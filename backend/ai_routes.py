"""Phase 5 endpoints: /ai/..."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import get_db
import ai_recommender as ai

router = APIRouter(prefix="/ai", tags=["ai"])


def _get_or_create(db: Session, anomaly_id: int, force: bool) -> Dict[str, Any]:
    existing = db.query(ai.Recommendation).filter_by(anomaly_id=anomaly_id).first()
    if existing and not force:
        return ai.recommendation_to_dict(existing)
    anomaly = ai.load_anomaly(db, anomaly_id)
    if anomaly is None:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    ctx = ai.build_context(db, anomaly)
    rec = ai.generate_recommendation(ctx)
    row = ai.save_recommendation(db, anomaly_id, ctx["service_id"], rec)
    return ai.recommendation_to_dict(row)


@router.get("/status")
def ai_status():
    """Kaun sa mode chal raha hai: llm ya rule-based."""
    return ai.get_ai_status()


@router.post("/recommend/{anomaly_id}")
def recommend(anomaly_id: int, force: bool = False, db: Session = Depends(get_db)):
    """Ek anomaly ki recommendation. Pehle se saved ho to wahi deta hai (force=true se dobara banta hai)."""
    return _get_or_create(db, anomaly_id, force)


@router.post("/recommend-top")
def recommend_top(limit: int = 3, force: bool = False, db: Session = Depends(get_db)):
    """Sabse zyada score wali anomalies ki recommendations (max 10, taaki API ka kharcha kam rahe)."""
    limit = max(1, min(limit, 10))
    ids = [r[0] for r in db.execute(
        text("SELECT id FROM anomalies ORDER BY score DESC LIMIT :n"), {"n": limit}
    ).all()]
    if not ids:
        raise HTTPException(status_code=404, detail="No anomalies found. Run POST /ml/detect first.")
    return [_get_or_create(db, i, force) for i in ids]


@router.get("/recommendations")
def list_recommendations(limit: int = 50, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    rows = (
        db.query(ai.Recommendation)
        .order_by(ai.Recommendation.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [ai.recommendation_to_dict(r) for r in rows]