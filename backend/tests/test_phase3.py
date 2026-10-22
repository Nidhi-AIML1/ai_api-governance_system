"""Phase 3 ka quick test. Chalane ke liye (backend/ folder se):  python tests/test_phase3.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import networkx as nx
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def get_service_id(name: str) -> int:
    r = client.get("/services")
    assert r.status_code == 200
    for s in r.json():
        if s["name"] == name:
            return s["id"]
    raise AssertionError(f"Service '{name}' nahi mila DB mein")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_graph_returns_nodes_and_edges():
    r = client.get("/graph")
    assert r.status_code == 200, r.text
    data = r.json()

    assert "nodes" in data, "Response mein 'nodes' key nahi hai"
    assert "edges" in data, "Response mein 'edges' key nahi hai"
    assert len(data["nodes"]) >= 6, f"Kam se kam 6 nodes chahiye, mili: {len(data['nodes'])}"
    assert len(data["edges"]) > 0,  "Koi edge nahi mila — traffic_generator pehle chalao"

    # Edge structure check
    edge = data["edges"][0]
    assert "source"               in edge
    assert "target"               in edge
    assert "call_count"           in edge
    assert "avg_response_time_ms" in edge
    assert "error_rate"           in edge
    assert edge["call_count"] > 0

    print(f"  graph: {len(data['nodes'])} nodes, {len(data['edges'])} edges")


def test_critical_services_ordering():
    r = client.get("/graph/critical")
    assert r.status_code == 200, r.text
    data = r.json()

    assert isinstance(data, list)
    assert len(data) >= 6

    # Sabse pehle wala service sabse zyada critical hona chahiye
    if len(data) > 1:
        assert data[0]["total_dependents"] >= data[1]["total_dependents"], \
            "Critical ranking galat hai — total_dependents descending hona chahiye"

    # Required fields
    for item in data:
        assert "service_name"        in item
        assert "direct_dependents"   in item
        assert "indirect_dependents" in item
        assert "total_dependents"    in item

    print(f"  critical: top 3 = {[d['service_name'] for d in data[:3]]}")


def test_graph_impact_payment_service():
    """payment-service fail hone par kaun affected hoga."""
    pay_id = get_service_id("payment-service")

    r = client.get(f"/graph/impact/{pay_id}")
    assert r.status_code == 200, r.text
    data = r.json()

    assert data["service_id"]   == pay_id
    assert data["service_name"] == "payment-service"
    assert "direct_dependents"  in data
    assert "indirect_dependents" in data
    assert "total_affected"     in data
    assert "message"            in data

    # order-service ne payment-service ko call kiya hai traffic data mein
    direct_names = [d["service_name"] for d in data["direct_dependents"]]
    assert "order-service" in direct_names, \
        f"order-service ko direct dependent hona chahiye payment ka, mila: {direct_names}"

    print(f"  impact(payment-service): total_affected={data['total_affected']}, "
          f"direct={direct_names}")


def test_graph_impact_404():
    r = client.get("/graph/impact/99999")
    assert r.status_code == 404, f"404 expected, mila: {r.status_code}"
    print("  impact 404 check PASS")


def test_no_real_cycles():
    """
    Hamara traffic data acyclic hai (login->user, order->user/payment/inventory,
    payment->notification, order->notification). Koi cycle nahi honi chahiye.
    """
    r = client.get("/graph/cycles")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "cycle_count" in data
    assert "cycles"      in data
    # Real data mein koi cycle nahi honi chahiye
    assert data["cycle_count"] == 0, \
        f"Real data mein cycles nahi hone chahiye, mili: {data['cycles']}"
    print(f"  cycles in real data: {data['cycle_count']} (expected 0) PASS")


def test_cycle_detection_with_synthetic_graph():
    """
    Real DB mein cycle inject kiye bina, networkx graph mein manually cycle banao
    aur verify karo ki simple_cycles detect karti hai.
    """
    G = nx.DiGraph()
    # A -> B -> C -> A  (deliberate cycle)
    G.add_edges_from([(1, 2), (2, 3), (3, 1)])
    # D -> E            (no cycle)
    G.add_edges_from([(4, 5)])

    cycles = list(nx.simple_cycles(G))
    # Ek hi elementary cycle honi chahiye: [1,2,3] (ya koi rotation)
    assert len(cycles) == 1, f"Exactly 1 cycle expected, mili: {cycles}"

    cycle_sets = [frozenset(c) for c in cycles]
    assert frozenset([1, 2, 3]) in cycle_sets, \
        f"Expected cycle {{1,2,3}}, mili: {cycles}"

    print(f"  synthetic cycle detection PASS: found {cycles}")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run():
    tests = [
        ("Graph returns nodes and edges",        test_graph_returns_nodes_and_edges),
        ("Critical services ordering",           test_critical_services_ordering),
        ("Impact: payment-service",              test_graph_impact_payment_service),
        ("Impact: 404 for unknown service",      test_graph_impact_404),
        ("No cycles in real data",               test_no_real_cycles),
        ("Cycle detection (synthetic graph)",    test_cycle_detection_with_synthetic_graph),
    ]

    passed = failed = 0
    for name, fn in tests:
        try:
            print(f"\n[TEST] {name}")
            fn()
            print(f"  PASS")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Phase 3 Tests: {passed} passed, {failed} failed")
    if failed == 0:
        print("Phase 3 tests PASS")
    else:
        print("Kuch tests fail hue — upar output dekho!")
        sys.exit(1)


if __name__ == "__main__":
    run()
