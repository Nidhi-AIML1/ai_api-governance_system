"""
Dependency Graph Router – Phase 3
Endpoints:
    GET /graph                          – full graph (nodes + edges)
    GET /graph/critical                 – services ranked by downstream dependents
    GET /graph/cycles                   – circular dependency detection
    GET /graph/impact/{service_id}      – blast-radius if a service fails
"""

from typing import Any

import networkx as nx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import ApiLog, Service

router = APIRouter(prefix="/graph", tags=["graph"])


# ---------------------------------------------------------------------------
# Core helper: build a DiGraph from the DB
# ---------------------------------------------------------------------------
def _build_graph(db: Session) -> tuple[nx.DiGraph, dict[int, str]]:
    """
    api_logs table se directed graph banao.
    Edge direction: caller_service_id --> service_id  (caller -> callee)
    NULL caller wale rows ignore hote hain (external client calls).

    Returns:
        G        – networkx DiGraph (nodes are service IDs)
        id_name  – {service_id: service_name} mapping
    """
    # All services (so isolated nodes also appear in the graph)
    services = db.query(Service).all()
    id_name: dict[int, str] = {s.id: s.name for s in services}

    G = nx.DiGraph()
    for svc in services:
        G.add_node(svc.id, name=svc.name, service_id=svc.id)

    # Aggregate edges from logs (NULL caller rows skip ho jaate hain)
    rows = (
        db.query(
            ApiLog.caller_service_id,
            ApiLog.service_id,
            ApiLog.status_code,
            ApiLog.response_time_ms,
        )
        .filter(ApiLog.caller_service_id.isnot(None))
        .all()
    )

    # Accumulate per (caller, callee)
    edge_data: dict[tuple[int, int], dict] = {}
    for caller_id, callee_id, status, rt in rows:
        key = (caller_id, callee_id)
        if key not in edge_data:
            edge_data[key] = {"call_count": 0, "total_rt": 0.0, "errors": 0}
        edge_data[key]["call_count"] += 1
        edge_data[key]["total_rt"] += rt
        if status >= 500:
            edge_data[key]["errors"] += 1

    for (caller_id, callee_id), agg in edge_data.items():
        count = agg["call_count"]
        G.add_edge(
            caller_id,
            callee_id,
            call_count=count,
            avg_response_time_ms=round(agg["total_rt"] / count, 2),
            error_rate=round(agg["errors"] / count, 4),
        )

    return G, id_name


# ---------------------------------------------------------------------------
# GET /graph
# ---------------------------------------------------------------------------
@router.get("")
def get_graph(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Full dependency graph – nodes and edges.
    Frontend future mein is data se graph draw karega.
    """
    G, id_name = _build_graph(db)

    nodes = [
        {"id": nid, "name": id_name.get(nid, str(nid))}
        for nid in G.nodes()
    ]

    edges = []
    for src, tgt, data in G.edges(data=True):
        edges.append({
            "source":               src,
            "source_name":          id_name.get(src, str(src)),
            "target":               tgt,
            "target_name":          id_name.get(tgt, str(tgt)),
            "call_count":           data["call_count"],
            "avg_response_time_ms": data["avg_response_time_ms"],
            "error_rate":           data["error_rate"],
        })

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# GET /graph/critical
# ---------------------------------------------------------------------------
@router.get("/critical")
def get_critical_services(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """
    Services ko rank karo by how many other services depend on them
    (directly + indirectly).

    Logic: ek service jitni zyada services ke liye ancestor hai (in reverse
    graph = predecessor in forward graph), utna zyada critical hai.
    networkx.descendants(G, node) gives all nodes reachable FROM node, so we
    use the REVERSE graph to find all nodes that depend ON a node.
    """
    G, id_name = _build_graph(db)
    R = G.reverse(copy=True)   # reverse: edge aata hai callee <- caller

    result = []
    for nid in G.nodes():
        # Sab services jo is node par depend karti hain (direct + indirect)
        dependents = nx.descendants(R, nid)
        direct     = set(G.predecessors(nid))          # jo directly call karte hain
        indirect   = dependents - direct

        result.append({
            "service_id":            nid,
            "service_name":          id_name.get(nid, str(nid)),
            "direct_dependents":     len(direct),
            "indirect_dependents":   len(indirect),
            "total_dependents":      len(dependents),
        })

    # Sabse critical pehle (total dependents descending, tiebreak by direct)
    result.sort(key=lambda x: (-x["total_dependents"], -x["direct_dependents"]))
    return result


# ---------------------------------------------------------------------------
# GET /graph/cycles
# ---------------------------------------------------------------------------
@router.get("/cycles")
def get_cycles(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Circular dependencies dhundo (A -> B -> A).
    networkx.simple_cycles returns all elementary circuits.
    Names ke saath return karte hain taaki readable ho.
    """
    G, id_name = _build_graph(db)

    raw_cycles = list(nx.simple_cycles(G))

    named_cycles = []
    for cycle in raw_cycles:
        named_cycles.append({
            "cycle_ids":   cycle,
            "cycle_names": [id_name.get(nid, str(nid)) for nid in cycle],
        })

    return {
        "cycle_count": len(named_cycles),
        "cycles":      named_cycles,
    }


# ---------------------------------------------------------------------------
# GET /graph/impact/{service_id}
# ---------------------------------------------------------------------------
@router.get("/impact/{service_id}")
def get_impact(service_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Agar ye service fail ho jaaye to kaun kaun affected hoga?
    Direct dependents  = jo seedha is service ko call karte hain.
    Indirect dependents = jo is service ke through kisi aur ko reach karte hain.

    Logic: reverse graph mein service_id se reachable nodes = dependents.
    """
    svc = db.get(Service, service_id)
    if not svc:
        raise HTTPException(status_code=404, detail=f"Service {service_id} nahi mila")

    G, id_name = _build_graph(db)
    R = G.reverse(copy=True)

    # Nodes that reach service_id in forward graph = predecessors (direct callers)
    direct_ids   = set(G.predecessors(service_id))

    # All nodes that depend on service_id (direct + indirect) via reverse graph
    all_dep_ids  = nx.descendants(R, service_id)
    indirect_ids = all_dep_ids - direct_ids

    def _fmt(ids: set) -> list[dict]:
        return sorted(
            [{"service_id": i, "service_name": id_name.get(i, str(i))} for i in ids],
            key=lambda x: x["service_name"],
        )

    return {
        "service_id":          service_id,
        "service_name":        svc.name,
        "direct_dependents":   _fmt(direct_ids),
        "indirect_dependents": _fmt(indirect_ids),
        "total_affected":      len(all_dep_ids),
        "message": (
            f"'{svc.name}' fail hone par {len(all_dep_ids)} service(s) affected hongi."
            if all_dep_ids else
            f"'{svc.name}' par koi service depend nahi karti."
        ),
    }
