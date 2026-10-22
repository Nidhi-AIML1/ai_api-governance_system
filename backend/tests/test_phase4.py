"""
Phase 4 Tests – ML Anomaly Detection
Chalane ke liye (backend/ folder se):
    python tests/test_phase4.py
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from sklearn.ensemble import IsolationForest

from main import app
from ml import (
    FEATURE_COLUMNS,
    ServiceAwareScaler,
    build_features_from_df,
)

client = TestClient(app)


# ---------------------------------------------------------------------------
# Test 1: Feature building on small synthetic dataset
# ---------------------------------------------------------------------------
def test_feature_building_synthetic():
    t0 = datetime(2026, 10, 14, 10, 0, 0)
    # 3 logs in 10:00 - 10:05 window for service 1
    # 2 logs in 10:05 - 10:10 window for service 1
    # 2 logs in 10:00 - 10:05 window for service 2 (including one 500 error)
    data = [
        {"service_id": 1, "response_time_ms": 50.0,  "status_code": 200, "timestamp": t0 + timedelta(seconds=10)},
        {"service_id": 1, "response_time_ms": 100.0, "status_code": 200, "timestamp": t0 + timedelta(seconds=70)},
        {"service_id": 1, "response_time_ms": 150.0, "status_code": 200, "timestamp": t0 + timedelta(seconds=120)},
        {"service_id": 1, "response_time_ms": 80.0,  "status_code": 200, "timestamp": t0 + timedelta(minutes=5, seconds=10)},
        {"service_id": 1, "response_time_ms": 120.0, "status_code": 200, "timestamp": t0 + timedelta(minutes=6, seconds=20)},
        {"service_id": 2, "response_time_ms": 200.0, "status_code": 200, "timestamp": t0 + timedelta(seconds=30)},
        {"service_id": 2, "response_time_ms": 400.0, "status_code": 500, "timestamp": t0 + timedelta(seconds=90)},
    ]
    df = pd.DataFrame(data)
    features = build_features_from_df(df)

    assert len(features) == 3, f"Expected 3 windows, got: {len(features)}"
    for col in ["service_id", "window_start", "window_end"] + FEATURE_COLUMNS:
        assert col in features.columns, f"Missing column {col}"

    # Window 1: service 1 at 10:00
    w1 = features[(features["service_id"] == 1) & (features["window_start"] == pd.Timestamp(t0))].iloc[0]
    assert w1["request_count"] == 3
    assert w1["avg_response_ms"] == 100.0  # (50 + 100 + 150) / 3
    assert w1["max_response_ms"] == 150.0
    assert w1["error_rate"] == 0.0

    # Window 3: service 2 at 10:00
    w2 = features[(features["service_id"] == 2) & (features["window_start"] == pd.Timestamp(t0))].iloc[0]
    assert w2["request_count"] == 2
    assert w2["avg_response_ms"] == 300.0  # (200 + 400) / 2
    assert w2["max_response_ms"] == 400.0
    assert w2["error_rate"] == 0.5  # 1 out of 2 is >= 500

    print("  feature building on synthetic data PASS")


# ---------------------------------------------------------------------------
# Test 2: Clearly abnormal window is flagged by Isolation Forest
# ---------------------------------------------------------------------------
def test_abnormal_window_flagged():
    np.random.seed(42)
    # Generate 40 normal windows for service 1 (~80ms, 0 errors)
    rows = []
    t_start = datetime(2026, 10, 1, 0, 0, 0)
    for i in range(40):
        rows.append({
            "service_id": 1,
            "window_start": t_start + timedelta(minutes=5 * i),
            "window_end": t_start + timedelta(minutes=5 * (i + 1)),
            "request_count": int(np.random.randint(10, 25)),
            "avg_response_ms": float(np.random.normal(80, 5)),
            "p95_response_ms": float(np.random.normal(95, 6)),
            "max_response_ms": float(np.random.normal(120, 10)),
            "error_rate": 0.0,
        })

    # Add 1 massive outlier window: latency 1500ms, error_rate 0.8
    rows.append({
        "service_id": 1,
        "window_start": t_start + timedelta(minutes=5 * 40),
        "window_end": t_start + timedelta(minutes=5 * 41),
        "request_count": 30,
        "avg_response_ms": 1500.0,
        "p95_response_ms": 1800.0,
        "max_response_ms": 2200.0,
        "error_rate": 0.8,
    })

    df = pd.DataFrame(rows)
    scaler = ServiceAwareScaler()
    scaled = scaler.fit_transform(df, FEATURE_COLUMNS)

    iso = IsolationForest(contamination=0.05, random_state=42)
    iso.fit(scaled)
    preds = iso.predict(scaled)
    scores = -iso.score_samples(scaled)

    # Last row is our extreme outlier
    outlier_pred = preds[-1]
    outlier_score = scores[-1]
    normal_scores = scores[:-1]

    assert outlier_pred == -1, f"Expected outlier to be flagged (-1), got {outlier_pred}"
    assert outlier_score > np.percentile(normal_scores, 95), \
        f"Outlier score {outlier_score} should exceed normal 95th percentile"

    print(f"  abnormal window flagged PASS: score={outlier_score:.4f} vs normal avg={np.mean(normal_scores):.4f}")


# ---------------------------------------------------------------------------
# Test 3: Endpoint /ml/train
# ---------------------------------------------------------------------------
def test_ml_train_endpoint():
    r = client.post("/ml/train", params={"contamination": 0.02})
    assert r.status_code == 200, r.text
    data = r.json()
    assert "windows_used" in data
    assert "contamination" in data
    assert "trained_at" in data
    assert data["windows_used"] > 1000, f"Expected >1000 windows, got: {data['windows_used']}"
    assert data["contamination"] == 0.02

    print(f"  POST /ml/train PASS: {data['windows_used']} windows used")


# ---------------------------------------------------------------------------
# Test 4: Endpoint /ml/model-info
# ---------------------------------------------------------------------------
def test_ml_model_info_endpoint():
    r = client.get("/ml/model-info")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["algorithm"] == "IsolationForest"
    assert "features" in data
    assert "windows_count" in data
    assert "trained_at" in data
    assert data["windows_count"] > 1000

    print(f"  GET /ml/model-info PASS: algorithm={data['algorithm']}, features={data['features']}")


# ---------------------------------------------------------------------------
# Test 5: Endpoint /ml/detect
# ---------------------------------------------------------------------------
def test_ml_detect_endpoint():
    r = client.post("/ml/detect")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "anomalies_detected" in data
    assert data["anomalies_detected"] > 0, "No anomalies detected"

    print(f"  POST /ml/detect PASS: {data['anomalies_detected']} anomalies saved to DB")


# ---------------------------------------------------------------------------
# Test 6: Endpoint /ml/anomalies (listing & filtering)
# ---------------------------------------------------------------------------
def test_ml_anomalies_endpoint():
    # Full list
    r = client.get("/ml/anomalies", params={"limit": 10})
    assert r.status_code == 200, r.text
    data = r.json()
    assert isinstance(data, list)
    assert len(data) > 0

    # Ensure sorted by score descending
    scores = [item["score"] for item in data]
    assert scores == sorted(scores, reverse=True), "Anomalies must be sorted by score descending"

    first = data[0]
    for key in ["id", "service_id", "service_name", "window_start", "window_end", "score", "avg_response_ms", "error_rate"]:
        assert key in first, f"Missing key {key} in anomaly item"

    # Filter by service_id
    sid = first["service_id"]
    r_filtered = client.get("/ml/anomalies", params={"service_id": sid, "limit": 10})
    assert r_filtered.status_code == 200
    filtered_data = r_filtered.json()
    for item in filtered_data:
        assert item["service_id"] == sid, f"Expected service_id {sid}, got {item['service_id']}"

    print(f"  GET /ml/anomalies PASS: top score={scores[0]}, filtered service count={len(filtered_data)}")


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------
def run():
    tests = [
        ("Feature building on synthetic dataset", test_feature_building_synthetic),
        ("Clearly abnormal window flagged",      test_abnormal_window_flagged),
        ("POST /ml/train endpoint",               test_ml_train_endpoint),
        ("GET /ml/model-info endpoint",           test_ml_model_info_endpoint),
        ("POST /ml/detect endpoint",              test_ml_detect_endpoint),
        ("GET /ml/anomalies endpoint",            test_ml_anomalies_endpoint),
    ]

    passed = failed = 0
    for name, fn in tests:
        try:
            print(f"\n[TEST] {name}")
            fn()
            print("  PASS")
            passed += 1
        except AssertionError as e:
            print(f"  FAIL: {e}")
            failed += 1
        except Exception as e:
            import traceback
            print(f"  ERROR: {e}")
            traceback.print_exc()
            failed += 1

    print(f"\n{'=' * 50}")
    print(f"Phase 4 Tests: {passed} passed, {failed} failed")
    if failed == 0:
        print("Phase 4 tests PASS")
    else:
        print("Kuch tests fail hue — upar output dekho!")
        sys.exit(1)


if __name__ == "__main__":
    run()
