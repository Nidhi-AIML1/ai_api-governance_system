"""
API Governance module

Ye module "kya hona chahiye" (documented APIs aur documented dependencies) ko
"kya sach mein ho raha hai" (logs) se compare karta hai aur problems nikalta hai:

  1. Dependency drift   : documented architecture se alag calls (undocumented ya purani dependency)
  2. Unused APIs        : API catalog mein hai par logs mein ek bhi call nahi
  3. Broken APIs        : bahut zyada 5xx ya 404 dene wali APIs
  4. Undocumented APIs  : calls aa rahi hain par catalog mein nahi hain (shadow APIs)
  5. Security risks     : 401/403 ka burst, aur unexpected service ka sensitive API call karna
  6. Performance        : bahut slow (p95) endpoints

Scan apne aap bhi chalta hai (autonomous), har GOVERNANCE_SCAN_MINUTES minute mein (default 15).
Note: security wala hissa logs se "risk signals" nikalta hai. Ye vulnerability scanner nahi hai.
"""

import json
import os
import random
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from models import ApiLog, Service

# ---------------------------------------------------------------------------
# Thresholds (yahin se badal sakti ho)
# ---------------------------------------------------------------------------
HIDDEN_PREFIX = "test-service-"     # tests wali bekaar services ignore hoti hain
MIN_CALLS_FOR_RATES = 20            # error / speed ka faisla karne ke liye kam se kam calls
BROKEN_ERROR_RATE = 0.10            # 10% se zyada 5xx  -> Broken API
BROKEN_HIGH_RATE = 0.30             # 30% se zyada      -> High severity
NOT_FOUND_RATE = 0.50               # 50% se zyada 404  -> route broken
PERF_P95_MS = 500                   # p95 500 ms se zyada -> Performance bottleneck
PERF_HIGH_P95_MS = 1000             # 1000 ms se zyada -> High severity
MIN_CALLS_SHADOW = 5                # itni calls ho to undocumented API maani jayegi
MIN_EDGE_CALLS = 5                  # itni calls ho to dependency "observed" maani jayegi
AUTH_FAIL_BUCKET = 10               # 5 minute mein itne 401/403 -> burst
AUTH_HIGH_TOTAL = 50                # burst mein itne ya zyada -> High
SENSITIVE_WORDS = ("admin", "refund", "token", "auth", "password", "delete", "charge", "/pay")
SEVERITY_WEIGHT = {"Critical": 10, "High": 5, "Medium": 2, "Low": 1}
MAX_STORED_SCANS = 50

CATEGORIES = [
    "dependency_drift",
    "unused_api",
    "broken_api",
    "undocumented_api",
    "security",
    "performance",
]

# Demo data ke liye (seed_demo)
UNUSED_EXTRAS = [
    ("user-service", "GET", "/users/export"),
    ("order-service", "DELETE", "/orders/bulk"),
    ("inventory-service", "GET", "/stock/legacy"),
    ("payment-service", "POST", "/v1/charge"),
]
SEEDED_ENDPOINTS = [
    ("login-service", "POST", "/auth/token"),
    ("inventory-service", "POST", "/reserve-legacy"),
    ("payment-service", "POST", "/admin/refund"),
]


# ---------------------------------------------------------------------------
# Naye tables (purane tables ko touch nahi karte)
# ---------------------------------------------------------------------------
class ApiCatalogEntry(Base):
    """Documented APIs ki list: kaun si service ki kaun si API officially maujood hai."""
    __tablename__ = "api_catalog"
    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, nullable=False, index=True)
    endpoint = Column(String, nullable=False)
    method = Column(String, nullable=False)
    __table_args__ = (UniqueConstraint("service_id", "endpoint", "method", name="uq_api_catalog"),)


class DocumentedDependency(Base):
    """Documented architecture: kaun si service kis service ko call karni chahiye."""
    __tablename__ = "documented_dependencies"
    id = Column(Integer, primary_key=True, index=True)
    caller_service_id = Column(Integer, nullable=False)
    callee_service_id = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("caller_service_id", "callee_service_id", name="uq_doc_dependency"),)


class GovernanceScan(Base):
    """Har scan ka result (autonomous scans ki history)."""
    __tablename__ = "governance_scans"
    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, nullable=False)
    trigger = Column(String, nullable=False)
    result_json = Column(Text, nullable=False)


Base.metadata.create_all(
    bind=engine,
    tables=[ApiCatalogEntry.__table__, DocumentedDependency.__table__, GovernanceScan.__table__],
)


# ---------------------------------------------------------------------------
# Chhote helpers
# ---------------------------------------------------------------------------
def _percentile(sorted_values: List[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * pct / 100
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def _naive(ts: datetime) -> datetime:
    return ts.replace(tzinfo=None) if ts.tzinfo else ts


def _floor5(ts: datetime) -> datetime:
    ts = _naive(ts)
    return ts.replace(minute=ts.minute - ts.minute % 5, second=0, microsecond=0)


def _fmt(ts: datetime) -> str:
    return _naive(ts).strftime("%d %b %H:%M") + " UTC"


def _iso(ts: Optional[datetime]) -> Optional[str]:
    return _naive(ts).isoformat() + "Z" if ts else None


def _finding(key, category, severity, service, title, detail, recommendation) -> Dict[str, Any]:
    return {
        "id": key,
        "category": category,
        "severity": severity,
        "service": service,
        "title": title,
        "detail": detail,
        "recommendation": recommendation,
    }


def _is_sensitive(endpoint: str) -> bool:
    e = endpoint.lower()
    return any(w in e for w in SENSITIVE_WORDS)


Key = Tuple[int, str, str]  # (service_id, endpoint, method)


# ---------------------------------------------------------------------------
# Logs se numbers (pure functions: seedhe test ho sakte hain)
# rows = (service_id, caller_service_id, endpoint, method, status_code, response_time_ms, timestamp)
# ---------------------------------------------------------------------------
def endpoint_stats(rows) -> Dict[Key, Dict[str, Any]]:
    acc: Dict[Key, Dict[str, Any]] = defaultdict(lambda: {"times": [], "errors": 0, "not_found": 0})
    for sid, _caller, ep, method, status, rt, _ts in rows:
        a = acc[(sid, ep, method)]
        a["times"].append(float(rt))
        if status >= 500:
            a["errors"] += 1
        if status == 404:
            a["not_found"] += 1
    out: Dict[Key, Dict[str, Any]] = {}
    for key, a in acc.items():
        times = sorted(a["times"])
        n = len(times)
        out[key] = {
            "calls": n,
            "error_rate": a["errors"] / n,
            "not_found_rate": a["not_found"] / n,
            "avg_ms": sum(times) / n,
            "p95_ms": _percentile(times, 95),
        }
    return out


def edge_stats(rows) -> Tuple[Counter, Dict[Tuple[int, int], Counter]]:
    """(caller, callee) ki calls, aur har edge par kaun kaun si API call hui."""
    counts: Counter = Counter()
    endpoints: Dict[Tuple[int, int], Counter] = defaultdict(Counter)
    for sid, caller, ep, method, _status, _rt, _ts in rows:
        if caller is None or caller == sid:
            continue
        counts[(caller, sid)] += 1
        endpoints[(caller, sid)][(method, ep)] += 1
    return counts, endpoints


# ---------------------------------------------------------------------------
# Checks (pure functions)
# ---------------------------------------------------------------------------
def check_unused(names, catalog_keys: Set[Key], stats) -> List[Dict[str, Any]]:
    out = []
    for sid, ep, method in sorted(catalog_keys):
        if sid not in names or (sid, ep, method) in stats:
            continue
        svc = names[sid]
        out.append(_finding(
            f"unused_api:{sid}:{method}:{ep}", "unused_api",
            "Low", svc,
            f"Unused API: {method} {ep}",
            f"{method} {ep} is listed in the API catalog of {svc}, but no call to it was found in the logs.",
            "Check whether any client still needs it. If not, deprecate and remove it to cut maintenance work and attack surface.",
        ))
    return out


def check_undocumented_apis(names, catalog_keys: Set[Key], stats) -> List[Dict[str, Any]]:
    out = []
    for (sid, ep, method), s in sorted(stats.items()):
        if sid not in names or (sid, ep, method) in catalog_keys or s["calls"] < MIN_CALLS_SHADOW:
            continue
        svc = names[sid]
        out.append(_finding(
            f"undocumented_api:{sid}:{method}:{ep}", "undocumented_api", "Medium", svc,
            f"Undocumented API: {method} {ep}",
            f"{svc} received {s['calls']} calls to {method} {ep}, but this API is missing from the API catalog.",
            "Add it to the API documentation. If nobody should be using it, block it.",
        ))
    return out


def check_broken(names, stats) -> List[Dict[str, Any]]:
    out = []
    for (sid, ep, method), s in sorted(stats.items()):
        if sid not in names or s["calls"] < MIN_CALLS_FOR_RATES:
            continue
        svc = names[sid]
        if s["error_rate"] >= BROKEN_ERROR_RATE:
            sev = "High" if s["error_rate"] >= BROKEN_HIGH_RATE else "Medium"
            out.append(_finding(
                f"broken_api:{sid}:{method}:{ep}", "broken_api", sev, svc,
                f"Broken API: {method} {ep}",
                f"{s['error_rate'] * 100:.0f}% of {s['calls']} calls to {method} {ep} returned server errors (5xx).",
                "Read the 5xx logs of this endpoint, find the failing dependency or recent release, then fix it or disable the endpoint until it is fixed.",
            ))
        elif s["not_found_rate"] >= NOT_FOUND_RATE:
            out.append(_finding(
                f"broken_api:{sid}:{method}:{ep}", "broken_api", "Medium", svc,
                f"Broken route: {method} {ep}",
                f"{s['not_found_rate'] * 100:.0f}% of {s['calls']} calls to {method} {ep} returned 404 (not found).",
                "Clients are calling a route that does not exist. Fix the route, or update the clients.",
            ))
    return out


def is_broken(s: Dict[str, Any]) -> bool:
    return s["calls"] >= MIN_CALLS_FOR_RATES and (
        s["error_rate"] >= BROKEN_ERROR_RATE or s["not_found_rate"] >= NOT_FOUND_RATE)


def check_performance(names, stats) -> List[Dict[str, Any]]:
    out = []
    for (sid, ep, method), s in sorted(stats.items()):
        if sid not in names or s["calls"] < MIN_CALLS_FOR_RATES or s["p95_ms"] < PERF_P95_MS:
            continue
        if is_broken(s):  # broken API pehle hi report ho chuki hai, dobara nahi ginte
            continue
        svc = names[sid]
        out.append(_finding(
            f"performance:{sid}:{method}:{ep}", "performance",
            "High" if s["p95_ms"] >= PERF_HIGH_P95_MS else "Medium", svc,
            f"Performance bottleneck: {method} {ep}",
            f"p95 response time is {s['p95_ms']:.0f} ms (average {s['avg_ms']:.0f} ms) over {s['calls']} calls.",
            "Profile the slowest queries and downstream calls, add caching, and set timeouts so slow calls do not pile up.",
        ))
    return out


def check_dependencies(names, documented: Set[Tuple[int, int]], counts: Counter):
    """Documented architecture vs observed architecture. Returns (findings, drift_percent, observed_set)."""
    observed = {e for e, n in counts.items() if n >= MIN_EDGE_CALLS and e[0] in names and e[1] in names}
    documented = {e for e in documented if e[0] in names and e[1] in names}
    out: List[Dict[str, Any]] = []
    if not documented:
        return out, None, observed

    for caller, callee in sorted(observed - documented):
        n = counts[(caller, callee)]
        out.append(_finding(
            f"dependency_drift:undocumented:{caller}:{callee}", "dependency_drift", "Medium", names[caller],
            f"Undocumented dependency: {names[caller]} calls {names[callee]}",
            f"{names[caller]} called {names[callee]} {n} times, but this dependency is not in the documented architecture.",
            "Document the dependency if it is intended. If it is not, remove the call and review who added it.",
        ))
    for caller, callee in sorted(documented - observed):
        out.append(_finding(
            f"dependency_drift:stale:{caller}:{callee}", "dependency_drift", "Low", names[caller],
            f"Documented dependency never used: {names[caller]} to {names[callee]}",
            f"The architecture documents say {names[caller]} calls {names[callee]}, but no calls were observed.",
            "Either the documentation is outdated, or the integration is broken. Check which one and fix it.",
        ))
    union = observed | documented
    drift = (len(observed ^ documented) / len(union) * 100.0) if union else 0.0
    return out, round(drift, 1), observed


def check_security(names, rows, documented: Set[Tuple[int, int]], endpoints_by_edge) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    # (a) 401/403 ka burst: 5 minute ke buckets
    buckets: Dict[Tuple[int, datetime], Counter] = defaultdict(Counter)
    for sid, _caller, ep, _method, status, _rt, ts in rows:
        if status in (401, 403) and sid in names:
            buckets[(sid, _floor5(ts))][ep] += 1
    by_service: Dict[int, List[Tuple[datetime, Counter]]] = defaultdict(list)
    for (sid, b), c in buckets.items():
        if sum(c.values()) >= AUTH_FAIL_BUCKET:
            by_service[sid].append((b, c))
    for sid, items in by_service.items():
        items.sort(key=lambda x: x[0])
        groups: List[List[Tuple[datetime, Counter]]] = []
        for item in items:
            if groups and item[0] - groups[-1][-1][0] <= timedelta(minutes=10):
                groups[-1].append(item)
            else:
                groups.append([item])
        for g in groups:
            total = sum(sum(c.values()) for _, c in g)
            top_ep = sum((c for _, c in g), Counter()).most_common(1)[0][0]
            start, end = g[0][0], g[-1][0] + timedelta(minutes=5)
            out.append(_finding(
                f"security:auth_burst:{sid}:{_naive(start).isoformat()}", "security",
                "High" if total >= AUTH_HIGH_TOTAL else "Medium", names[sid],
                f"Burst of authentication failures on {top_ep}",
                f"{total} requests were rejected with 401/403 on {names[sid]} {top_ep} between {_fmt(start)} and {_fmt(end)}. "
                "This pattern can mean password guessing, or a client with a broken credential.",
                "Rate-limit the endpoint, alert on repeated failures from one source, and check whether the caller is a known client.",
            ))

    # (b) documented na hone wali service ka sensitive API call karna
    if documented:
        for (caller, callee), eps in sorted(endpoints_by_edge.items()):
            if (caller, callee) in documented or caller not in names or callee not in names:
                continue
            for (method, ep), n in sorted(eps.items()):
                if n >= 3 and _is_sensitive(ep):
                    out.append(_finding(
                        f"security:unexpected_caller:{caller}:{callee}:{method}:{ep}", "security", "High", names[callee],
                        f"Unexpected service calling a sensitive API: {names[caller]} to {method} {ep}",
                        f"{names[caller]} called {names[callee]} {method} {ep} {n} times, but {names[caller]} is not documented to use {names[callee]}.",
                        "Check that this access is intended. Protect service-to-service calls with authentication and an allow-list of callers.",
                    ))
    return out


# ---------------------------------------------------------------------------
# Data collect + poora scan
# ---------------------------------------------------------------------------
def _collect(db: Session):
    names = {s.id: s.name for s in db.query(Service).all() if not s.name.startswith(HIDDEN_PREFIX)}
    rows = [
        r for r in db.query(
            ApiLog.service_id, ApiLog.caller_service_id, ApiLog.endpoint, ApiLog.method,
            ApiLog.status_code, ApiLog.response_time_ms, ApiLog.timestamp,
        ).all()
        if r[0] in names
    ]
    catalog_keys = {(c.service_id, c.endpoint, c.method) for c in db.query(ApiCatalogEntry).all()}
    documented = {(d.caller_service_id, d.callee_service_id) for d in db.query(DocumentedDependency).all()}
    return names, rows, catalog_keys, documented


def is_setup(db: Session) -> bool:
    return db.query(ApiCatalogEntry).count() > 0 and db.query(DocumentedDependency).count() > 0


def _grade(score: int) -> str:
    return "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"


def build_scan(names, rows, catalog_keys, documented) -> Dict[str, Any]:
    stats = endpoint_stats(rows)
    counts, edge_eps = edge_stats(rows)
    has_catalog = bool(catalog_keys)

    findings: List[Dict[str, Any]] = []
    if has_catalog:
        findings += check_unused(names, catalog_keys, stats)
        findings += check_undocumented_apis(names, catalog_keys, stats)
    findings += check_broken(names, stats)
    findings += check_performance(names, stats)
    dep_findings, drift, observed_edges = check_dependencies(names, documented, counts)
    findings += dep_findings
    findings += check_security(names, rows, documented, edge_eps)

    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    findings.sort(key=lambda f: (order[f["severity"]], f["category"], f["title"]))

    broken_keys = {k for k, s in stats.items() if is_broken(s)}
    inventory = []
    for key in sorted(set(stats) | {k for k in catalog_keys if k[0] in names}, key=lambda k: (names.get(k[0], ""), k[1], k[2])):
        sid, ep, method = key
        s = stats.get(key)
        if s is None:
            state = "Unused"
        elif has_catalog and key not in catalog_keys and s["calls"] >= MIN_CALLS_SHADOW:
            state = "Undocumented"
        elif key in broken_keys:
            state = "Broken"
        else:
            state = "Active"
        inventory.append({
            "service": names[sid], "endpoint": ep, "method": method,
            "calls": s["calls"] if s else 0,
            "error_rate": round(s["error_rate"], 4) if s else 0.0,
            "p95_ms": round(s["p95_ms"], 1) if s else 0.0,
            "documented": (key in catalog_keys) if has_catalog else None,
            "state": state,
        })

    edges = []
    for a, b in sorted(observed_edges | documented):
        if a not in names or b not in names:
            continue
        if not documented:
            state = "observed"
        elif (a, b) in observed_edges and (a, b) in documented:
            state = "ok"
        elif (a, b) in observed_edges:
            state = "undocumented"
        else:
            state = "stale"
        edges.append({"source": a, "target": b, "source_name": names[a], "target_name": names[b],
                      "calls": counts.get((a, b), 0), "state": state})

    by_sev = Counter(f["severity"] for f in findings)
    by_cat = Counter(f["category"] for f in findings)
    score = max(0, 100 - sum(SEVERITY_WEIGHT[f["severity"]] for f in findings))
    stamps = [r[6] for r in rows]

    return {
        "data_period": {"first": _iso(min(stamps)) if stamps else None, "last": _iso(max(stamps)) if stamps else None},
        "summary": {
            "score": score,
            "grade": _grade(score),
            "total_findings": len(findings),
            "by_severity": {k: by_sev.get(k, 0) for k in ("Critical", "High", "Medium", "Low")},
            "by_category": {k: by_cat.get(k, 0) for k in CATEGORIES},
            "drift_percent": drift,
            "apis_observed": len(stats),
            "apis_documented": len(catalog_keys),
            "dependencies_observed": len(observed_edges),
            "dependencies_documented": len(documented),
            "setup_complete": has_catalog and bool(documented),
        },
        "findings": findings,
        "inventory": inventory,
        "architecture": {"nodes": [{"id": i, "name": n} for i, n in sorted(names.items())], "edges": edges},
    }


def run_scan(db: Session, trigger: str = "manual") -> Dict[str, Any]:
    names, rows, catalog_keys, documented = _collect(db)
    result = build_scan(names, rows, catalog_keys, documented)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = GovernanceScan(created_at=now, trigger=trigger, result_json=json.dumps(result))
    db.add(row)
    db.commit()
    db.refresh(row)
    # sirf aakhri MAX_STORED_SCANS scans rakho
    old = db.query(GovernanceScan.id).order_by(GovernanceScan.id.desc()).offset(MAX_STORED_SCANS).all()
    if old:
        db.query(GovernanceScan).filter(GovernanceScan.id.in_([o[0] for o in old])).delete(synchronize_session=False)
        db.commit()
    result["scan_id"] = row.id
    result["created_at"] = _iso(row.created_at)
    result["trigger"] = trigger
    return result


def latest_scan(db: Session) -> Optional[Dict[str, Any]]:
    row = db.query(GovernanceScan).order_by(GovernanceScan.id.desc()).first()
    if row is None:
        return None
    result = json.loads(row.result_json)
    result["scan_id"] = row.id
    result["created_at"] = _iso(row.created_at)
    result["trigger"] = row.trigger
    return result


def list_scans(db: Session, limit: int = 10) -> List[Dict[str, Any]]:
    rows = db.query(GovernanceScan).order_by(GovernanceScan.id.desc()).limit(max(1, min(limit, 50))).all()
    out = []
    for r in rows:
        summary = json.loads(r.result_json)["summary"]
        out.append({"id": r.id, "created_at": _iso(r.created_at), "trigger": r.trigger,
                    "score": summary["score"], "grade": summary["grade"], "total_findings": summary["total_findings"]})
    return out


# ---------------------------------------------------------------------------
# Demo data (nakli): catalog, documented dependencies aur kuch extra traffic
# ---------------------------------------------------------------------------
def _seed_keys(db: Session) -> Set[Tuple[int, str, str]]:
    ids = {s.name: s.id for s in db.query(Service).all()}
    return {(ids[n], ep, m) for n, m, ep in SEEDED_ENDPOINTS if n in ids}


def remove_demo(db: Session) -> Dict[str, int]:
    removed_logs = 0
    for sid, ep, m in _seed_keys(db):
        removed_logs += db.query(ApiLog).filter(
            ApiLog.service_id == sid, ApiLog.endpoint == ep, ApiLog.method == m
        ).delete(synchronize_session=False)
    cat = db.query(ApiCatalogEntry).delete(synchronize_session=False)
    dep = db.query(DocumentedDependency).delete(synchronize_session=False)
    scans = db.query(GovernanceScan).delete(synchronize_session=False)
    db.commit()
    return {"logs_removed": removed_logs, "catalog_entries_removed": cat,
            "dependencies_removed": dep, "scans_removed": scans}


def seed_demo(db: Session) -> Dict[str, Any]:
    ids = {s.name: s.id for s in db.query(Service).all() if not s.name.startswith(HIDDEN_PREFIX)}
    first, last = db.query(ApiLog.timestamp).order_by(ApiLog.timestamp.asc()).first(), \
        db.query(ApiLog.timestamp).order_by(ApiLog.timestamp.desc()).first()
    if not first or not ids:
        raise ValueError("No services or logs found. Create the data first (traffic generator).")

    remove_demo(db)  # dobara chalane par purana demo data hata do
    t0, t1 = _naive(first[0]), _naive(last[0])
    span = t1 - t0
    rng = random.Random(42)

    def at(frac: float, jitter_minutes: float = 0.0) -> datetime:
        return t0 + span * frac + timedelta(minutes=rng.uniform(0, jitter_minutes))

    # 1) Pehle jo dependencies sach mein hain (seed logs se pehle)
    names_by_id = {v: k for k, v in ids.items()}
    base_rows = [r for r in db.query(ApiLog.service_id, ApiLog.caller_service_id).all() if r[0] in names_by_id]
    base_counts = Counter((c, s) for s, c in base_rows if c is not None and c != s and c in names_by_id)
    observed_edges = {e for e, n in base_counts.items() if n >= MIN_EDGE_CALLS}

    # 2) Extra traffic
    new_logs: List[ApiLog] = []

    def add(sid, caller, ep, method, status, rt, ts):
        new_logs.append(ApiLog(service_id=sid, caller_service_id=caller, endpoint=ep, method=method,
                               status_code=status, response_time_ms=round(rt, 1), timestamp=ts))

    if "login-service" in ids:  # security: auth failures ka burst
        sid = ids["login-service"]
        for _ in range(30):
            add(sid, None, "/auth/token", "POST", 200, rng.gauss(45, 8), at(rng.random()))
        burst = 0.72
        for _ in range(85):
            add(sid, None, "/auth/token", "POST", 401 if rng.random() < 0.75 else 403, abs(rng.gauss(30, 8)), at(burst, 12))
    if "inventory-service" in ids:  # broken API
        sid = ids["inventory-service"]
        caller = ids.get("order-service")
        for _ in range(90):
            r = rng.random()
            if r < 0.55:
                add(sid, caller, "/reserve-legacy", "POST", 500, rng.gauss(900, 100), at(rng.random()))
            elif r < 0.70:
                add(sid, caller, "/reserve-legacy", "POST", 503, rng.gauss(900, 100), at(rng.random()))
            else:
                add(sid, caller, "/reserve-legacy", "POST", 200, rng.gauss(220, 60), at(rng.random()))
    if "payment-service" in ids and "inventory-service" in ids:  # unexpected caller
        sid = ids["payment-service"]
        for _ in range(16):
            add(sid, ids["inventory-service"], "/admin/refund", "POST", 200 if rng.random() < 0.6 else 403,
                abs(rng.gauss(140, 20)), at(0.9, 40))
    db.add_all(new_logs)
    db.commit()

    # 3) API catalog: jo APIs sach mein dikhi, unme se ek ko documentation se bahar rakho (shadow API)
    rows = [r for r in db.query(ApiLog.service_id, ApiLog.endpoint, ApiLog.method).all() if r[0] in names_by_id]
    obs = Counter((s, e, m) for s, e, m in rows)
    seeded = _seed_keys(db)
    shadow = None
    for svc_name in ("notification-service", "user-service", *ids.keys()):
        if svc_name not in ids:
            continue
        candidates = sorted(((n, k) for k, n in obs.items()
                             if k[0] == ids[svc_name] and k not in seeded and n >= MIN_CALLS_SHADOW))
        if candidates:
            shadow = candidates[0][1]
            break
    catalog = {k for k in obs if k != shadow}
    for n, m, ep in UNUSED_EXTRAS:
        if n in ids and (ids[n], ep, m) not in obs:
            catalog.add((ids[n], ep, m))
    for sid, ep, m in sorted(catalog):
        db.add(ApiCatalogEntry(service_id=sid, endpoint=ep, method=m))

    # 4) Documented architecture: sach wali dependencies, ek kam (undocumented), ek extra (stale)
    documented = set(observed_edges)
    removed = None
    pref = (ids.get("order-service"), ids.get("notification-service"))
    if pref in documented:
        removed = pref
    elif documented:
        removed = min(documented, key=lambda e: base_counts[e])
    if removed:
        documented.discard(removed)
    stale = None
    pairs = [(ids.get("payment-service"), ids.get("notification-service"))] + \
            [(a, b) for a in ids.values() for b in ids.values() if a != b]
    for p in pairs:
        if None not in p and p not in observed_edges and p != removed:
            stale = p
            break
    if stale:
        documented.add(stale)
    for a, b in sorted(documented):
        db.add(DocumentedDependency(caller_service_id=a, callee_service_id=b))
    db.commit()

    return {
        "logs_added": len(new_logs),
        "catalog_entries": len(catalog),
        "documented_dependencies": len(documented),
        "undocumented_api_example": f"{shadow[2]} {shadow[1]} on {names_by_id[shadow[0]]}" if shadow else None,
        "left_out_of_docs": f"{names_by_id[removed[0]]} to {names_by_id[removed[1]]}" if removed else None,
        "documented_but_unused": f"{names_by_id[stale[0]]} to {names_by_id[stale[1]]}" if stale else None,
    }


# ---------------------------------------------------------------------------
# Autonomous scan: apne aap, ek timer par
# ---------------------------------------------------------------------------
_started = False


def scan_interval_minutes() -> int:
    try:
        return max(1, int(os.environ.get("GOVERNANCE_SCAN_MINUTES", "15")))
    except ValueError:
        return 15


def autoscan_enabled() -> bool:
    return os.environ.get("GOVERNANCE_AUTOSCAN", "1") != "0"


def start_autoscan() -> None:
    global _started
    if _started or not autoscan_enabled():
        return
    _started = True

    def loop() -> None:
        time.sleep(8)
        while True:
            try:
                db = SessionLocal()
                try:
                    if is_setup(db):
                        run_scan(db, trigger="auto")
                finally:
                    db.close()
            except Exception as exc:  # scan fail ho to server band nahi hona chahiye
                print("[governance] auto-scan failed:", exc)
            time.sleep(scan_interval_minutes() * 60)

    threading.Thread(target=loop, daemon=True, name="governance-autoscan").start()