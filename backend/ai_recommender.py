"""
AI Recommendation Module - Phase 5
Anomaly milne par ye module batata hai:
  - problem ka summary
  - probable causes
  - impact (kaun kaun si services affect hongi)
  - suggested fixes
  - priority (Low / Medium / High / Critical)

Do modes:
  1. LLM mode  : agar .env mein ANTHROPIC_API_KEY ho, Claude API se recommendation aati hai.
  2. Rule mode : key na ho (ya API fail ho jaye) to rules se recommendation banti hai.
                 Is mode ke liye internet ya paise ki zarurat nahi.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy import Column, DateTime, Integer, String, Text, case, func, text
from sqlalchemy.orm import Session

from database import Base, engine
from models import ApiLog, Service

# ---------------------------------------------------------------------------
# Settings (.env file se, har call par padhi jati hai - restart nahi chahiye)
# ---------------------------------------------------------------------------
ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-haiku-5-5"   # sasta aur tez. .env mein AI_MODEL se badal sakti ho.
ALLOWED_PRIORITIES = ["Low", "Medium", "High", "Critical"]


def get_setting(name: str, default: str = "") -> str:
    """Pehle environment variable, phir backend/.env file."""
    value = os.environ.get(name)
    if value is not None:
        return value.strip()
    try:
        with open(ENV_PATH, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                if key.strip() == name:
                    return val.strip().strip('"').strip("'")
    except OSError:
        pass
    return default


def get_ai_status() -> Dict[str, Any]:
    has_key = bool(get_setting("ANTHROPIC_API_KEY"))
    return {
        "mode": "llm" if has_key else "rule-based",
        "api_key_found": has_key,
        "model": get_setting("AI_MODEL", DEFAULT_MODEL) if has_key else None,
        "note": (
            "Claude API se recommendations aayengi (fail hone par rule-based fallback)."
            if has_key
            else "API key nahi mili, isliye rule-based recommendations use ho rahi hain."
        ),
    }


# ---------------------------------------------------------------------------
# Database table: recommendations (naya table, purane tables ko touch nahi karta)
# ---------------------------------------------------------------------------
class Recommendation(Base):
    __tablename__ = "recommendations"
    id = Column(Integer, primary_key=True, index=True)
    anomaly_id = Column(Integer, unique=True, nullable=False, index=True)
    service_id = Column(Integer, nullable=False)
    source = Column(String, nullable=False)
    priority = Column(String)
    summary = Column(Text)
    probable_causes = Column(Text)   # JSON list
    impact = Column(Text)
    suggested_fixes = Column(Text)   # JSON list
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


Base.metadata.create_all(bind=engine, tables=[Recommendation.__table__])


# ---------------------------------------------------------------------------
# Context building: anomaly + service ka normal behaviour + dependencies
# ---------------------------------------------------------------------------
def load_anomaly(db: Session, anomaly_id: int) -> Optional[Dict[str, Any]]:
    row = db.execute(
        text(
            "SELECT id, service_id, window_start, window_end, score, "
            "avg_response_ms, error_rate FROM anomalies WHERE id = :i"
        ),
        {"i": anomaly_id},
    ).mappings().first()
    return dict(row) if row else None


def build_context(db: Session, anomaly: Dict[str, Any]) -> Dict[str, Any]:
    sid = int(anomaly["service_id"])
    service = db.get(Service, sid)
    name = service.name if service else f"service-{sid}"

    total, avg_rt, errors = db.query(
        func.count(ApiLog.id),
        func.avg(ApiLog.response_time_ms),
        func.sum(case((ApiLog.status_code >= 500, 1), else_=0)),
    ).filter(ApiLog.service_id == sid).one()
    base_avg = float(avg_rt or 0.0)
    base_err_pct = (float(errors or 0) / total * 100.0) if total else 0.0

    # Dependency info (Phase 3 ke graph se). Graph na mile to khali list.
    depends_on: List[str] = []
    called_by: List[str] = []
    affected: List[str] = []
    try:
        import networkx as nx
        from graph import _build_graph

        G, id_name = _build_graph(db)
        if sid in G:
            depends_on = sorted(id_name.get(n, str(n)) for n in G.successors(sid))
            called_by = sorted(id_name.get(n, str(n)) for n in G.predecessors(sid))
            affected = sorted(id_name.get(n, str(n)) for n in nx.ancestors(G, sid))
    except Exception:
        pass

    obs_avg = float(anomaly.get("avg_response_ms") or 0.0)
    obs_err_pct = float(anomaly.get("error_rate") or 0.0) * 100.0
    ratio = (obs_avg / base_avg) if base_avg > 0 else 1.0

    return {
        "anomaly_id": int(anomaly["id"]),
        "service": name,
        "service_id": sid,
        "window_start": str(anomaly.get("window_start")),
        "window_end": str(anomaly.get("window_end")),
        "anomaly_score": round(float(anomaly.get("score") or 0.0), 4),
        "observed": {"avg_response_ms": round(obs_avg, 1), "error_rate_pct": round(obs_err_pct, 1)},
        "normal": {"avg_response_ms": round(base_avg, 1), "error_rate_pct": round(base_err_pct, 1)},
        "latency_ratio": round(ratio, 2),
        "depends_on": depends_on,
        "called_by_directly": called_by,
        "all_services_affected_if_it_fails": affected,
    }


# ---------------------------------------------------------------------------
# Rule-based recommendation (key ke bina bhi kaam karta hai)
# ---------------------------------------------------------------------------
def classify_issue(ctx: Dict[str, Any]) -> str:
    latency = ctx["latency_ratio"] >= 2.0
    obs_err = ctx["observed"]["error_rate_pct"]
    err = obs_err >= 15 and obs_err >= 3 * ctx["normal"]["error_rate_pct"]
    if latency and err:
        return "latency_and_errors"
    if latency:
        return "latency"
    if err:
        return "errors"
    return "unusual"


def _priority(ctx: Dict[str, Any], kind: str) -> str:
    points = 0
    if kind in ("latency", "latency_and_errors"):
        points += 2 if ctx["latency_ratio"] >= 4 else 1
    if kind in ("errors", "latency_and_errors"):
        points += 2 if ctx["observed"]["error_rate_pct"] >= 30 else 1
    n = len(ctx["all_services_affected_if_it_fails"])
    if n >= 1:
        points += 1
    if n >= 3:
        points += 1
    if points >= 5:
        return "Critical"
    if points >= 3:
        return "High"
    if points >= 2:
        return "Medium"
    return "Low"


def rule_based_recommendation(ctx: Dict[str, Any]) -> Dict[str, Any]:
    kind = classify_issue(ctx)
    svc = ctx["service"]
    deps = ctx["depends_on"]
    deps_txt = ", ".join(deps)
    obs, nor = ctx["observed"], ctx["normal"]

    if kind == "latency":
        summary = (
            f"{svc} became unusually slow between {ctx['window_start']} and {ctx['window_end']}: "
            f"average response time was {obs['avg_response_ms']} ms, about {ctx['latency_ratio']}x "
            f"its normal {nor['avg_response_ms']} ms."
        )
    elif kind == "errors":
        summary = (
            f"{svc} returned many server errors between {ctx['window_start']} and {ctx['window_end']}: "
            f"error rate was {obs['error_rate_pct']}% against a normal {nor['error_rate_pct']}%."
        )
    elif kind == "latency_and_errors":
        summary = (
            f"{svc} was both slow and failing between {ctx['window_start']} and {ctx['window_end']}: "
            f"{obs['avg_response_ms']} ms average response ({ctx['latency_ratio']}x normal) and "
            f"{obs['error_rate_pct']}% errors."
        )
    else:
        summary = (
            f"{svc} behaved unusually between {ctx['window_start']} and {ctx['window_end']} "
            f"(anomaly score {ctx['anomaly_score']}), but neither latency nor error rate crossed a clear threshold."
        )

    causes: List[str] = []
    fixes: List[str] = []
    if kind in ("latency", "latency_and_errors"):
        causes.append(
            f"Likely a slow downstream dependency ({deps_txt})." if deps
            else f"Possible resource saturation (CPU, memory or thread pool) on {svc}."
        )
        causes += [
            "Possible slow database queries or missing indexes.",
            "Possible traffic spike or a recent deployment that introduced a performance regression.",
        ]
        fixes += [
            "Check deployments and config changes around this time window and roll back if the timing matches.",
            f"Look at the slowest endpoints of {svc} (GET /analytics/services/{ctx['service_id']}/endpoints) and optimise their queries or add caching.",
            "Check CPU and memory usage and scale out if the service is saturated.",
        ]
        if deps:
            fixes.append(f"Add timeouts, retries with backoff and a circuit breaker for calls to {deps_txt}.")
    if kind in ("errors", "latency_and_errors"):
        causes += [
            "Likely a failing dependency or database connection problem.",
            "Possible bad deployment or wrong configuration.",
            "Possible resource exhaustion (out of memory, too many connections).",
        ]
        fixes += [
            f"Read the 5xx error logs of {svc} for this window and group them by endpoint.",
            "Roll back or hotfix the latest change if errors started right after a release.",
            "Add graceful degradation (fallback responses) and a circuit breaker so failures do not spread.",
            "Check capacity and rate limits; enable autoscaling if load was high.",
        ]
    if kind == "unusual":
        causes = [
            "Possible short-lived traffic burst or a very quiet period.",
            "Possible one-off error that does not form a trend.",
        ]
        fixes = [
            "Watch the service for the next few windows to see if the pattern repeats.",
            f"Compare this window with GET /analytics/services/{ctx['service_id']}/timeseries.",
            "Consider ignoring it if it does not repeat.",
        ]

    # dedupe, order maintain
    fixes = list(dict.fromkeys(fixes))
    causes = list(dict.fromkeys(causes))

    if ctx["all_services_affected_if_it_fails"]:
        impact = (
            f"{svc} is called directly by {', '.join(ctx['called_by_directly']) or 'no service'}. "
            f"If the problem continues, these services can be affected too: "
            f"{', '.join(ctx['all_services_affected_if_it_fails'])}."
        )
    else:
        impact = (
            f"No other service depends on {svc} in the observed call graph, "
            f"so the impact is limited to its own users."
        )

    return {
        "summary": summary,
        "probable_causes": causes,
        "impact": impact,
        "suggested_fixes": fixes,
        "priority": _priority(ctx, kind),
    }


# ---------------------------------------------------------------------------
# LLM recommendation (Claude API, plain HTTP via httpx - koi extra package nahi)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = (
    "You are a senior site reliability engineer reviewing an anomaly found by a monitoring "
    "system on a microservice platform. Use ONLY the facts given. Do not invent metrics, "
    "service names or incidents. Be concise and practical. Respond with a single JSON object "
    "and nothing else."
)


def _user_prompt(ctx: Dict[str, Any]) -> str:
    return (
        "Anomaly data:\n"
        + json.dumps(ctx, indent=2)
        + "\n\nReturn JSON with exactly these keys:\n"
        '- "summary": 1-2 sentences\n'
        '- "probable_causes": list of 2-4 short strings, most likely first '
        "(these are hypotheses, word them as 'likely' or 'possible')\n"
        '- "impact": 1-2 sentences using called_by_directly and all_services_affected_if_it_fails\n'
        '- "suggested_fixes": list of 3-5 concrete actions\n'
        '- "priority": one of Low, Medium, High, Critical'
    )


def parse_llm_json(raw: str) -> Dict[str, Any]:
    """Model ke jawab se JSON nikalta hai (```json ... ``` ho to bhi)."""
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in AI response")
    data = json.loads(raw[start : end + 1])

    def as_list(v: Any) -> List[str]:
        if isinstance(v, list):
            return [str(x) for x in v]
        return [str(v)] if v else []

    priority = str(data.get("priority", "Medium")).strip().capitalize()
    if priority not in ALLOWED_PRIORITIES:
        priority = "Medium"
    result = {
        "summary": str(data.get("summary", "")).strip(),
        "probable_causes": as_list(data.get("probable_causes")),
        "impact": str(data.get("impact", "")).strip(),
        "suggested_fixes": as_list(data.get("suggested_fixes")),
        "priority": priority,
    }
    if not result["summary"] or not result["suggested_fixes"]:
        raise ValueError("AI response missing summary or suggested_fixes")
    return result


def llm_recommendation(ctx: Dict[str, Any]) -> Dict[str, Any]:
    key = get_setting("ANTHROPIC_API_KEY")
    model = get_setting("AI_MODEL", DEFAULT_MODEL)
    resp = httpx.post(
        API_URL,
        headers={
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
        json={
            "model": model,
            "max_tokens": 900,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": _user_prompt(ctx)}],
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    blocks = resp.json().get("content", [])
    raw = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    return parse_llm_json(raw)


def _short_reason(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        msg = ""
        try:
            msg = exc.response.json().get("error", {}).get("message", "")
        except Exception:
            pass
        return f"HTTP {exc.response.status_code} {msg}".strip()[:150]
    return f"{type(exc).__name__}: {exc}"[:150]


def generate_recommendation(ctx: Dict[str, Any]) -> Dict[str, Any]:
    """Key ho to Claude, warna (ya fail hone par) rules. Kabhi crash nahi karta."""
    if get_setting("ANTHROPIC_API_KEY"):
        try:
            rec = llm_recommendation(ctx)
            rec["source"] = f"llm ({get_setting('AI_MODEL', DEFAULT_MODEL)})"
            return rec
        except Exception as exc:
            rec = rule_based_recommendation(ctx)
            rec["source"] = f"rule-based (AI call failed: {_short_reason(exc)})"
            return rec
    rec = rule_based_recommendation(ctx)
    rec["source"] = "rule-based"
    return rec


# ---------------------------------------------------------------------------
# Save / load
# ---------------------------------------------------------------------------
def recommendation_to_dict(row: Recommendation) -> Dict[str, Any]:
    return {
        "id": row.id,
        "anomaly_id": row.anomaly_id,
        "service_id": row.service_id,
        "source": row.source,
        "priority": row.priority,
        "summary": row.summary,
        "probable_causes": json.loads(row.probable_causes or "[]"),
        "impact": row.impact,
        "suggested_fixes": json.loads(row.suggested_fixes or "[]"),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def save_recommendation(db: Session, anomaly_id: int, service_id: int, rec: Dict[str, Any]) -> Recommendation:
    row = db.query(Recommendation).filter_by(anomaly_id=anomaly_id).first()
    if row is None:
        row = Recommendation(anomaly_id=anomaly_id, service_id=service_id)
        db.add(row)
    row.source = rec["source"]
    row.priority = rec["priority"]
    row.summary = rec["summary"]
    row.probable_causes = json.dumps(rec["probable_causes"])
    row.impact = rec["impact"]
    row.suggested_fixes = json.dumps(rec["suggested_fixes"])
    row.created_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row