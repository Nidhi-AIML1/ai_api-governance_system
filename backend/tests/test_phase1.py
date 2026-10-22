"""Phase 1 ka quick test. Chalane ke liye (backend folder se):  python tests/test_phase1.py"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def run():
    name = "test-service-" + os.urandom(3).hex()
    r = client.post("/services", json={"name": name, "owner": "team-a"})
    assert r.status_code == 200, r.text
    sid = r.json()["id"]

    r = client.post("/services", json={"name": name})
    assert r.status_code == 400  # duplicate nahi banna chahiye

    r = client.post("/logs", json={"service_id": sid, "endpoint": "/pay", "method": "POST",
                                    "status_code": 200, "response_time_ms": 120})
    assert r.status_code == 200, r.text

    r = client.post("/logs", json={"service_id": 99999, "endpoint": "/x", "method": "GET",
                                    "status_code": 200, "response_time_ms": 10})
    assert r.status_code == 404  # galat service

    r = client.get("/logs", params={"service_id": sid})
    assert r.status_code == 200 and len(r.json()) == 1
    print("Phase 1 tests PASS")


if __name__ == "__main__":
    run()
