"""Phase 2 ka quick test. Chalane ke liye (backend/ folder se):  python tests/test_phase2.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_any_service_id() -> int:
    """DB mein koi bhi ek service ka id lo."""
    r = client.get("/services")
    assert r.status_code == 200, f"GET /services failed: {r.text}"
    services = r.json()
    assert len(services) > 0, "Koi service nahi mili — pehle traffic_generator.py chalao!"
    return services[0]["id"]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_summary():
    r = client.get("/analytics/summary")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "total_services" in data
    assert "total_requests" in data
    assert "overall_error_rate" in data
    assert "overall_avg_response_time_ms" in data
    assert data["total_services"] >= 6, "6 services honi chahiye (traffic generator ke baad)"
    assert data["total_requests"] >= 1000, f"Bahut kam requests hain: {data['total_requests']}"
    assert 0.0 <= data["overall_error_rate"] <= 1.0
    assert data["overall_avg_response_time_ms"] > 0
    print(f"  summary: {data['total_requests']:,} requests, "
          f"error_rate={data['overall_error_rate']:.3f}, "
          f"avg_rt={data['overall_avg_response_time_ms']:.1f}ms")


def test_service_stats():
    sid = get_any_service_id()

    # Default 24h
    r = client.get(f"/analytics/services/{sid}/stats")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["service_id"] == sid
    assert "avg_response_time_ms" in data
    assert "p95_response_time_ms" in data
    assert "p99_response_time_ms" in data
    assert "error_rate" in data
    assert data["p95_response_time_ms"] >= data["avg_response_time_ms"], "p95 avg se kam nahi ho sakta"

    # Custom hours (168h = last 7 days)
    r2 = client.get(f"/analytics/services/{sid}/stats", params={"hours": 168})
    assert r2.status_code == 200, r2.text
    data2 = r2.json()
    assert data2["total_requests"] >= data["total_requests"], \
        "7 days mein 24h se zyada ya barabar requests honi chahiye"
    print(f"  service {sid} stats (24h): {data['total_requests']} reqs, "
          f"p95={data['p95_response_time_ms']:.1f}ms, p99={data['p99_response_time_ms']:.1f}ms")


def test_service_stats_404():
    r = client.get("/analytics/services/99999/stats")
    assert r.status_code == 404, f"Galat service pe 404 aana chahiye, mila: {r.status_code}"
    print("  404 check PASS")


def test_health():
    r = client.get("/analytics/health")
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) >= 6, f"Kam se kam 6 services chahiye, mili: {len(data)}"

    statuses = {item["service_name"]: item["status"] for item in data}
    for item in data:
        assert item["status"] in ("Healthy", "Warning", "Critical"), \
            f"Unknown status: {item['status']}"
        assert "error_rate" in item
        assert "p95_response_time_ms" in item
        assert "reason" in item

    print(f"  health check: {len(data)} services evaluated")
    for name, status in statuses.items():
        print(f"    {name}: {status}")


def test_endpoint_stats():
    sid = get_any_service_id()
    r = client.get(f"/analytics/services/{sid}/endpoints", params={"hours": 168})
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0, "Koi endpoint stats nahi mili"

    # Pehla item sabse slow hona chahiye (sorted by p95 desc)
    if len(data) > 1:
        assert data[0]["p95_response_time_ms"] >= data[1]["p95_response_time_ms"], \
            "Sorting galat hai — p95 descending order mein hona chahiye"

    for ep in data:
        assert "endpoint" in ep
        assert "method" in ep
        assert "total_requests" in ep
        assert "error_rate" in ep

    print(f"  endpoint stats: {len(data)} endpoints, "
          f"slowest={data[0]['endpoint']} p95={data[0]['p95_response_time_ms']:.1f}ms")


def test_timeseries():
    sid = get_any_service_id()
    r = client.get(f"/analytics/services/{sid}/timeseries",
                   params={"hours": 168, "interval_minutes": 60})
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0, "Timeseries empty nahi honi chahiye"

    # Should have ~168 buckets (could be 169 with rounding)
    assert 160 <= len(data) <= 175, f"Expected ~168 buckets, mili: {len(data)}"

    for bucket in data:
        assert "bucket_start" in bucket
        assert "total_requests" in bucket
        assert "avg_response_time_ms" in bucket
        assert "error_rate" in bucket
        assert 0.0 <= bucket["error_rate"] <= 1.0

    non_empty = [b for b in data if b["total_requests"] > 0]
    print(f"  timeseries: {len(data)} buckets, {len(non_empty)} non-empty")


def test_timeseries_404():
    r = client.get("/analytics/services/99999/timeseries")
    assert r.status_code == 404
    print("  timeseries 404 check PASS")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def run():
    tests = [
        ("Summary endpoint",       test_summary),
        ("Service stats endpoint",  test_service_stats),
        ("Service stats 404",       test_service_stats_404),
        ("Health endpoint",         test_health),
        ("Endpoint stats",          test_endpoint_stats),
        ("Timeseries endpoint",     test_timeseries),
        ("Timeseries 404",          test_timeseries_404),
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
            print(f"  ERROR: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Phase 2 Tests: {passed} passed, {failed} failed")
    if failed == 0:
        print("Phase 2 tests PASS")
    else:
        print("Kuch tests fail hue — upar output dekho!")
        sys.exit(1)


if __name__ == "__main__":
    run()
