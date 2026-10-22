"""
ML Anomaly Detection Router – Phase 4
Endpoints:
    POST /ml/train
    POST /ml/detect
    GET  /ml/anomalies?service_id=&limit=
    GET  /ml/model-info
"""

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import Anomaly, Service
from ml import (
    detect_anomalies,
    is_model_trained,
    load_artifacts,
    train_and_save_model,
)

router = APIRouter(prefix="/ml", tags=["ml"])


@router.post("/train")
def train(
    contamination: Optional[float] = Query(None, description="Expected proportion of anomalies"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Build 5-minute features from api_logs, train Isolation Forest model,
    save model & scaler to models_store/.
    """
    try:
        if contamination is not None:
            info = train_and_save_model(db, contamination=contamination)
        else:
            info = train_and_save_model(db)
        return {
            "message": "Model trained and saved successfully",
            "windows_used": info["windows_count"],
            "contamination": info["contamination"],
            "trained_at": info["trained_at"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {e}")


@router.post("/detect")
def detect(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """
    Run anomaly detection on all log windows, save detected anomalies
    to the 'anomalies' table (clearing old ones first).
    """
    if not is_model_trained():
        raise HTTPException(
            status_code=400,
            detail="Model has not been trained yet. Please call POST /ml/train first.",
        )

    try:
        anomalies, _ = detect_anomalies(db)

        # Clear old detected anomalies
        db.query(Anomaly).delete()
        db.commit()

        # Insert new anomalies
        for item in anomalies:
            record = Anomaly(
                service_id=item["service_id"],
                window_start=item["window_start"],
                window_end=item["window_end"],
                score=item["score"],
                avg_response_ms=item["avg_response_ms"],
                error_rate=item["error_rate"],
            )
            db.add(record)
        db.commit()

        return {
            "message": "Anomaly detection completed",
            "anomalies_detected": len(anomalies),
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Detection failed: {e}")


@router.get("/anomalies")
def get_anomalies(
    service_id: Optional[int] = Query(None, description="Filter by service_id"),
    limit: int = Query(100, ge=1, le=1000, description="Max anomalies to return"),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    List detected anomalies, highest score first.
    Returns clear 400 error if model is not trained yet.
    """
    if not is_model_trained():
        raise HTTPException(
            status_code=400,
            detail="Model has not been trained yet. Please call POST /ml/train first.",
        )

    query = (
        db.query(Anomaly, Service.name.label("service_name"))
        .join(Service, Anomaly.service_id == Service.id)
    )

    if service_id is not None:
        query = query.filter(Anomaly.service_id == service_id)

    rows = query.order_by(Anomaly.score.desc()).limit(limit).all()

    results = []
    for anom, sname in rows:
        results.append({
            "id": anom.id,
            "service_id": anom.service_id,
            "service_name": sname,
            "window_start": anom.window_start.isoformat() if anom.window_start else None,
            "window_end": anom.window_end.isoformat() if anom.window_end else None,
            "score": anom.score,
            "avg_response_ms": anom.avg_response_ms,
            "error_rate": anom.error_rate,
            "detected_at": anom.detected_at.isoformat() if anom.detected_at else None,
        })

    return results


@router.get("/model-info")
def get_model_info() -> Dict[str, Any]:
    """
    Returns metadata about the currently trained model:
    training date, number of windows, contamination, features used.
    """
    if not is_model_trained():
        raise HTTPException(
            status_code=404,
            detail="Model has not been trained yet. Please call POST /ml/train first.",
        )

    _, _, info = load_artifacts()
    return info
