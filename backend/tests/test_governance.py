"""API Governance ka test. Chalane ke liye (backend folder se):
    python tests/test_governance.py
Pehle ke hisse naqli data par chalte hain. Aakhri hissa asli database par scan chalata hai."""
import os
import sys
from collections import Counter
from datetime import datetime, timedelta

os.environ["GOVERNANCE_AUTOSCAN"] = "0"  # test ke dauran timer wala scan band
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import governance as gov

NAMES = {1: "login-service", 2: "order-service", 3: "payment-service"}
T0 = datetime(2026, 10, 10, 12, 0)


def row(sid, ep, method="GET", status=200, rt=100.0, caller=None, ts=T0):
    return (sid, caller, ep, method, status, rt, ts)


def run():
    # 1) Broken API: 50% 5xx -> High. 10 calls hi hon to faisla nahi hota.
    rows = [row(3, "/pay", "POST", 500 if i % 2 else 200) for i in range(30)]
    rows += [row(3, "/few", "GET", 500) for _ in range(10)]
    stats = gov.endpoint_stats(rows)
    broken = gov.check_broken(NAMES, stats)
    assert len(broken) == 1 and broken[0]["severity"] == "High" and "/pay" in broken[0]["title"]
    print("PASS broken API detection")

    # 2) Performance: 700 ms -> Medium, 1200 ms -> High. Broken endpoint dobara nahi ginta.
    rows = [row(3, "/slow", "GET", rt=700.0) for _ in range(25)]
    rows += [row(3, "/slower", "GET", rt=1200.0) for _ in range(25)]
    rows += [row(3, "/pay", "POST", status=500, rt=2000.0) for _ in range(25)]
    perf = gov.check_performance(NAMES, gov.endpoint_stats(rows))
    sev = {p["title"].split(": ")[1]: p["severity"] for p in perf}
    assert sev == {"GET /slow": "Medium", "GET /slower": "High"}, sev
    print("PASS performance bottlenecks")

    # 3) Unused aur undocumented APIs
    catalog = {(1, "/old", "GET")}
    stats = gov.endpoint_stats([row(1, "/new", "GET") for _ in range(6)] + [row(1, "/rare", "GET") for _ in range(4)])
    unused = gov.check_unused(NAMES, catalog, stats)
    shadow = gov.check_undocumented_apis(NAMES, catalog, stats)
    assert [u["title"] for u in unused] == ["Unused API: GET /old"]
    assert [s["title"] for s in shadow] == ["Undocumented API: GET /new"]  # 4 calls wali /rare nahi
    print("PASS unused and undocumented APIs")

    # 4) Dependency drift
    counts = Counter({(1, 2): 10, (2, 3): 20, (3, 1): 2})  # (3,1) mein 5 se kam calls: observed nahi
    findings, drift, observed = gov.check_dependencies(NAMES, {(1, 2)}, counts)
    assert observed == {(1, 2), (2, 3)}
    assert [f["title"] for f in findings] == ["Undocumented dependency: order-service calls payment-service"]
    assert drift == 50.0
    findings, drift, _ = gov.check_dependencies(NAMES, {(1, 2), (3, 1)}, counts)
    assert any(f["title"].startswith("Documented dependency never used") for f in findings)
    findings, drift, _ = gov.check_dependencies(NAMES, set(), counts)
    assert findings == [] and drift is None  # documented architecture na ho to drift nahi nikalta
    print("PASS dependency drift")

    # 5) Security: 401/403 ka burst
    few = [row(1, "/auth/token", "POST", 401, ts=T0 + timedelta(seconds=i)) for i in range(9)]
    burst = [row(1, "/auth/token", "POST", 401, ts=T0 + timedelta(seconds=i)) for i in range(12)]
    big = [row(1, "/auth/token", "POST", 403, ts=T0 + timedelta(seconds=i)) for i in range(60)]
    assert gov.check_security(NAMES, few, {(1, 2)}, {}) == []
    mid = gov.check_security(NAMES, burst, {(1, 2)}, {})
    high = gov.check_security(NAMES, big, {(1, 2)}, {})
    assert len(mid) == 1 and mid[0]["severity"] == "Medium"
    assert len(high) == 1 and high[0]["severity"] == "High"
    # Security: documented na hone wali service sensitive API call kare
    eps = {(2, 3): Counter({("POST", "/admin/refund"): 5, ("GET", "/status"): 50})}
    unexpected = gov.check_security(NAMES, [], {(1, 2)}, eps)
    assert len(unexpected) == 1 and "/admin/refund" in unexpected[0]["title"]
    assert gov.check_security(NAMES, [], {(1, 2), (2, 3)}, eps) == []  # documented ho to theek
    print("PASS security signals")

    # 6) Poora scan aur score
    rows = [row(3, "/pay", "POST", 500 if i % 2 else 200, caller=2) for i in range(30)]
    scan = gov.build_scan(NAMES, rows, set(), set())
    assert scan["summary"]["setup_complete"] is False
    assert scan["summary"]["by_severity"]["High"] == 1
    assert scan["summary"]["score"] == 100 - gov.SEVERITY_WEIGHT["High"]
    assert scan["summary"]["grade"] == "A"
    print("PASS scan and score")

    # 7) Asli database par endpoints (test ke baad demo data wapas hata deta hai agar test ne banaya ho)
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    r = client.get("/governance/status")
    if r.status_code == 404:
        print("SKIP endpoints: main.py mein governance_routes include nahi hua")
        return
    was_setup = r.json()["setup"]
    try:
        if not was_setup:
            seeded = client.post("/governance/seed-demo")
            if seeded.status_code == 400:
                print("SKIP endpoint flow: database mein logs nahi hain")
                return
            assert seeded.status_code == 200, seeded.text
        report = client.get("/governance/report").json()
        assert report["setup"] is True and report["scan"] is not None
        assert set(report["scan"]["summary"]["by_category"]) == set(gov.CATEGORIES)
        scan = client.post("/governance/scan").json()
        assert scan["trigger"] == "manual" and scan["scan_id"] > 0
        assert client.get("/governance/scans").json()[0]["id"] == scan["scan_id"]
        print("PASS endpoints")
    finally:
        if not was_setup:
            client.delete("/governance/seed-demo")
    print("Governance tests PASS")


if __name__ == "__main__":
    run()