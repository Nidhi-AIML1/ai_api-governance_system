"""Phase 5 ka test. Chalane ke liye (backend folder se):
    python tests/test_phase5.py
Is test mein asli Claude API kabhi call nahi hoti (naqli response use hota hai)."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx
import ai_recommender as ai

LATENCY_CTX = {
    "anomaly_id": 1, "service": "payment-service", "service_id": 4,
    "window_start": "2026-10-10 04:35:00", "window_end": "2026-10-10 04:40:00",
    "anomaly_score": 0.74,
    "observed": {"avg_response_ms": 800.0, "error_rate_pct": 2.0},
    "normal": {"avg_response_ms": 150.0, "error_rate_pct": 1.5},
    "latency_ratio": 5.33,
    "depends_on": ["notification-service"],
    "called_by_directly": ["order-service"],
    "all_services_affected_if_it_fails": ["order-service"],
}
ERROR_CTX = dict(LATENCY_CTX, service="inventory-service", service_id=5,
                 observed={"avg_response_ms": 76.0, "error_rate_pct": 45.0},
                 normal={"avg_response_ms": 75.0, "error_rate_pct": 2.0},
                 latency_ratio=1.01, depends_on=[])

FAKE_REPLY = {
    "summary": "payment-service slowed down.",
    "probable_causes": ["Likely slow notification-service."],
    "impact": "order-service may be affected.",
    "suggested_fixes": ["Check recent deploys.", "Add a timeout.", "Scale out."],
    "priority": "high",
}


class FakeResponse:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body or {}

    def json(self):
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("err", request=None, response=self)


def run():
    saved_key = os.environ.get("ANTHROPIC_API_KEY")
    real_post = httpx.post
    try:
        # 1) rule-based: latency
        os.environ["ANTHROPIC_API_KEY"] = ""
        assert ai.classify_issue(LATENCY_CTX) == "latency"
        rec = ai.generate_recommendation(LATENCY_CTX)
        assert rec["source"] == "rule-based"
        assert rec["priority"] in ai.ALLOWED_PRIORITIES
        assert "payment-service" in rec["summary"]
        assert len(rec["suggested_fixes"]) >= 3 and len(rec["probable_causes"]) >= 2
        assert "order-service" in rec["impact"]
        print("PASS rule-based latency")

        # 2) rule-based: errors
        assert ai.classify_issue(ERROR_CTX) == "errors"
        rec = ai.generate_recommendation(ERROR_CTX)
        assert "45.0%" in rec["summary"]
        print("PASS rule-based errors")

        # 3) JSON parsing (```json ... ``` ke saath bhi)
        parsed = ai.parse_llm_json("```json\n" + json.dumps(FAKE_REPLY) + "\n```")
        assert parsed["priority"] == "High"
        try:
            ai.parse_llm_json("no json here")
            raise AssertionError("should have failed")
        except ValueError:
            pass
        print("PASS json parsing")

        # 4) LLM path (naqli API reply)
        os.environ["ANTHROPIC_API_KEY"] = "test-key"
        httpx.post = lambda *a, **k: FakeResponse(200, {"content": [{"type": "text", "text": json.dumps(FAKE_REPLY)}]})
        rec = ai.generate_recommendation(LATENCY_CTX)
        assert rec["source"].startswith("llm"), rec["source"]
        assert rec["priority"] == "High"
        print("PASS llm path (mocked)")

        # 5) API fail -> rule-based fallback, crash nahi hona chahiye
        httpx.post = lambda *a, **k: FakeResponse(401, {"error": {"message": "invalid x-api-key"}})
        rec = ai.generate_recommendation(LATENCY_CTX)
        assert rec["source"].startswith("rule-based (AI call failed"), rec["source"]
        assert rec["summary"]
        print("PASS fallback on API error")
        httpx.post = real_post

        # 6) endpoints (asli database aur asli anomalies par)
        os.environ["ANTHROPIC_API_KEY"] = ""
        from fastapi.testclient import TestClient
        from main import app

        client = TestClient(app)
        r = client.get("/ai/status")
        if r.status_code == 404:
            print("SKIP endpoints: main.py mein ai_routes include nahi hua (README dekho)")
            return
        assert r.status_code == 200 and r.json()["mode"] == "rule-based"

        r = client.get("/ml/anomalies", params={"limit": 1})
        data = r.json() if r.status_code == 200 else []
        items = data if isinstance(data, list) else (data.get("anomalies") or data.get("items") or [])
        if not items or "id" not in items[0]:
            print("SKIP endpoint flow: koi anomaly nahi mili. Pehle /ml/train aur /ml/detect chalao.")
            return
        aid = items[0]["id"]
        r1 = client.post(f"/ai/recommend/{aid}")
        assert r1.status_code == 200, r1.text
        r2 = client.post(f"/ai/recommend/{aid}")
        assert r2.json()["id"] == r1.json()["id"]  # dobara banane ki jagah saved wali mili
        assert client.post("/ai/recommend/99999999").status_code == 404
        assert client.get("/ai/recommendations").status_code == 200
        print("PASS endpoints")
    finally:
        httpx.post = real_post
        if saved_key is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = saved_key
    print("Phase 5 tests PASS")


if __name__ == "__main__":
    run()