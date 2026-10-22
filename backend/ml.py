"""
ML Anomaly Detection Module – Phase 4
Contains:
  - 5-minute window feature aggregation per service
  - Service-aware feature scaling (StandardScaler)
  - Isolation Forest anomaly detection training and scoring
  - Model serialization to models_store/
"""

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session

from models import ApiLog, Service

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models_store")
MODEL_PATH = os.path.join(MODELS_DIR, "isolation_forest.pkl")
SCALER_PATH = os.path.join(MODELS_DIR, "scaler.pkl")
INFO_PATH = os.path.join(MODELS_DIR, "model_info.json")

FEATURE_COLUMNS = [
    "request_count",
    "avg_response_ms",
    "p95_response_ms",
    "max_response_ms",
    "error_rate",
]

MIN_REQUEST_COUNT = 2         # isse kam requests wale 5-minute windows ignore honge
DEFAULT_CONTAMINATION = 0.01  # model kitna sensitive rahe (0.01 = sabse ajeeb 1%)


class ServiceAwareScaler:
    """
    Per-service StandardScaler with global fallback.
    Standardizes each service's metrics independently so a naturally slow
    service (e.g., payment @ 150ms) is not penalized relative to a fast one
    (e.g., user @ 60ms).
    """

    def __init__(self):
        self.scalers: Dict[int, StandardScaler] = {}
        self.global_scaler: StandardScaler = StandardScaler()
        self.feature_cols: List[str] = FEATURE_COLUMNS

    def fit(self, df: pd.DataFrame, feature_cols: Optional[List[str]] = None) -> "ServiceAwareScaler":
        if feature_cols:
            self.feature_cols = feature_cols
        self.global_scaler.fit(df[self.feature_cols])

        for sid, group in df.groupby("service_id"):
            scaler = StandardScaler()
            scaler.fit(group[self.feature_cols])
            self.scalers[int(sid)] = scaler
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        scaled = np.zeros((len(df), len(self.feature_cols)), dtype=float)
        df_reset = df.reset_index(drop=True)

        for sid, group in df_reset.groupby("service_id"):
            idxs = group.index.to_numpy()
            scaler = self.scalers.get(int(sid), self.global_scaler)
            scaled[idxs] = scaler.transform(group[self.feature_cols])

        return scaled

    def fit_transform(self, df: pd.DataFrame, feature_cols: Optional[List[str]] = None) -> np.ndarray:
        return self.fit(df, feature_cols).transform(df)


# ---------------------------------------------------------------------------
# Feature Building
# ---------------------------------------------------------------------------
def build_features_from_df(df: pd.DataFrame, min_requests: int = 1) -> pd.DataFrame:
    """
    Given a DataFrame with columns ['service_id', 'response_time_ms', 'status_code', 'timestamp'],
    groups logs into 5-minute windows per service and computes:
      - request_count
      - avg_response_ms
      - p95_response_ms
      - max_response_ms
      - error_rate (status >= 500)
    Windows with fewer than `min_requests` requests are dropped.
    """
    if df.empty:
        return pd.DataFrame(columns=["service_id", "window_start", "window_end"] + FEATURE_COLUMNS)

    df = df.copy()
    df["ts"] = pd.to_datetime(df["timestamp"])
    # Floor to 5-minute boundaries
    df["window_start"] = df["ts"].dt.floor("5min")

    def _p95(series: pd.Series) -> float:
        if len(series) == 0:
            return 0.0
        return float(np.percentile(series, 95))

    grouped = df.groupby(["service_id", "window_start"])
    features = grouped.agg(
        request_count=("response_time_ms", "count"),
        avg_response_ms=("response_time_ms", "mean"),
        p95_response_ms=("response_time_ms", _p95),
        max_response_ms=("response_time_ms", "max"),
        error_count=("status_code", lambda s: int((s >= 500).sum())),
    ).reset_index()

    features["error_rate"] = features["error_count"] / features["request_count"]
    features["window_end"] = features["window_start"] + pd.Timedelta(minutes=5)

    # Clean numbers
    features["avg_response_ms"] = features["avg_response_ms"].round(2)
    features["p95_response_ms"] = features["p95_response_ms"].round(2)
    features["max_response_ms"] = features["max_response_ms"].round(2)
    features["error_rate"] = features["error_rate"].round(4)

    # Kam requests wale windows hatao (ek failed request se error_rate 1.0 ban jata hai)
    features = features[features["request_count"] >= min_requests].reset_index(drop=True)

    return features[["service_id", "window_start", "window_end"] + FEATURE_COLUMNS]


def build_features_from_db(db: Session) -> pd.DataFrame:
    """Load logs from db and compute 5-minute features."""
    logs = (
        db.query(
            ApiLog.service_id,
            ApiLog.response_time_ms,
            ApiLog.status_code,
            ApiLog.timestamp,
        )
        .all()
    )
    df = pd.DataFrame(
        logs,
        columns=["service_id", "response_time_ms", "status_code", "timestamp"],
    )
    return build_features_from_df(df, min_requests=MIN_REQUEST_COUNT)


# ---------------------------------------------------------------------------
# Training & Persistence
# ---------------------------------------------------------------------------
def train_and_save_model(
    db: Session,
    contamination: float = DEFAULT_CONTAMINATION,
    random_state: int = 42,
) -> Dict[str, Any]:
    """
    1. Builds features from all api_logs.
    2. Fits ServiceAwareScaler.
    3. Trains IsolationForest.
    4. Saves model, scaler, and metadata into models_store/.
    """
    os.makedirs(MODELS_DIR, exist_ok=True)

    features_df = build_features_from_db(db)
    if len(features_df) < 10:
        raise ValueError(f"Too few feature windows to train ({len(features_df)}). Need at least 10.")

    scaler = ServiceAwareScaler()
    scaled_matrix = scaler.fit_transform(features_df, FEATURE_COLUMNS)

    model = IsolationForest(
        contamination=contamination,
        random_state=random_state,
        n_estimators=100,
    )
    model.fit(scaled_matrix)

    now_iso = datetime.now(timezone.utc).isoformat()
    info = {
        "algorithm": "IsolationForest",
        "contamination": contamination,
        "random_state": random_state,
        "features": FEATURE_COLUMNS,
        "windows_count": int(len(features_df)),
        "min_request_count": MIN_REQUEST_COUNT,
        "trained_at": now_iso,
    }

    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    with open(INFO_PATH, "w") as f:
        json.dump(info, f, indent=2)

    return info


def load_artifacts() -> Tuple[IsolationForest, ServiceAwareScaler, Dict[str, Any]]:
    """Loads saved model, scaler, and info. Raises FileNotFoundError if missing."""
    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH) or not os.path.exists(INFO_PATH):
        raise FileNotFoundError("Model artifacts not found. Call /ml/train first.")

    model = joblib.load(MODEL_PATH)
    scaler = joblib.load(SCALER_PATH)
    with open(INFO_PATH, "r") as f:
        info = json.load(f)

    return model, scaler, info


def is_model_trained() -> bool:
    return os.path.exists(MODEL_PATH) and os.path.exists(SCALER_PATH) and os.path.exists(INFO_PATH)


# ---------------------------------------------------------------------------
# Anomaly Scoring and Detection
# ---------------------------------------------------------------------------
def detect_anomalies(db: Session) -> Tuple[List[Dict[str, Any]], pd.DataFrame]:
    """
    Loads trained model & scaler, builds features from DB, predicts anomalies,
    and returns list of detected anomaly records sorted by score descending.
    """
    model, scaler, _ = load_artifacts()
    features_df = build_features_from_db(db)

    if features_df.empty:
        return [], features_df

    scaled_matrix = scaler.transform(features_df)
    preds = model.predict(scaled_matrix)  # -1 = anomaly, 1 = normal
    # Higher score = more anomalous. -score_samples is in [0.35, 0.85+]
    scores = -model.score_samples(scaled_matrix)

    features_df = features_df.copy()
    features_df["is_anomaly"] = (preds == -1)
    features_df["score"] = [round(float(s), 4) for s in scores]

    anomalies_df = features_df[features_df["is_anomaly"]].sort_values(by="score", ascending=False)

    results: List[Dict[str, Any]] = []
    for _, row in anomalies_df.iterrows():
        # Ensure UTC timezone compatibility
        w_start = row["window_start"]
        w_end = row["window_end"]
        if hasattr(w_start, "to_pydatetime"):
            w_start = w_start.to_pydatetime()
        if hasattr(w_end, "to_pydatetime"):
            w_end = w_end.to_pydatetime()

        results.append({
            "service_id": int(row["service_id"]),
            "window_start": w_start,
            "window_end": w_end,
            "score": float(row["score"]),
            "avg_response_ms": float(row["avg_response_ms"]),
            "error_rate": float(row["error_rate"]),
        })

    return results, features_df