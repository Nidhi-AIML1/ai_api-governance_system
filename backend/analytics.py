"""
Analytics Router – Phase 2
Endpoints:
    GET /analytics/summary
    GET /analytics/data-range                       (Phase 6: data kis period ka hai)
    GET /analytics/services/{service_id}/stats?hours=24
    GET /analytics/health?hours=24
    GET /analytics/services/{service_id}/endpoints
    GET /analytics/services/{service_id}/timeseries?hours=24&interval_minutes=60
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import get_db
from models import ApiLog, Service

router = APIRouter(prefix="/analytics", tags=["analytics"])

# ---------------------------------------------------------------------------
# Health-check thresholds  (easy to tweak for Phase 4 ML integration)
# ---------------------------------------------------------------------------
HEALTHY_ERROR_RATE_MAX   = 0.05   # 5 %   error rate se kam  → Healthy
WARNING_ERROR_RATE_MAX   = 0.15   # 15%   error rate se kam  → Warning  (else Critical)

HEALTHY_P95_MAX_MS       = 500    # 500 ms p95 se kam         → Healthy
WARNING_P95_MAX_MS       = 1000   # 1000ms p95 se kam         → Warning  (else Critical)

# ---------------------------------------------------------------------------
# Pure-Python percentile (no NumPy needed)
# ---------------------------------------------------------------------------
def _percentile(sorted_values: list[float], pct: float) -> float:
    """
    Sorted list se pct-th percentile nikalo (0-100).
    Linear interpolation use hoti hai.
    """
    if not sorted_values:
        return 0.0
    k = (len(sorted_values) - 1) * pct / 100
    f, c = int(k), min(int(k) + 1, len(sorted_values) - 1)
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def _safe_avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _since(hours: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=hours)


# ---------------------------------------------------------------------------
# GET /analytics/summary
# ---------------------------------------------------------------------------
@router.get("/summary")
def get_summary(db: Session = Depends(get_db)) -> dict[str, Any]:
    """Total services, total requests, overall error rate, avg response time."""
    total_services  = db.query(Service).count()
    total_requests  = db.query(ApiLog).count()

    if total_requests == 0:
        return {
            "total_services":       total_services,
            "total_requests":       0,
            "overall_error_rate":   0.0,
            "overall_avg_response_time_ms": 0.0,
        }

    all_logs = db.query(ApiLog.status_code, ApiLog.response_time_ms).all()
    errors   = sum(1 for sc, _ in all_logs if sc >= 500)
    avg_rt   = _safe_avg([rt for _, rt in all_logs])

    return {
        "total_services":                total_services,
        "total_requests":                total_requests,
        "overall_error_rate":            round(errors / total_requests, 4),
        "overall_avg_response_time_ms":  round(avg_rt, 2),
    }


# ---------------------------------------------------------------------------
# GET /analytics/data-range   (Phase 6)
# ---------------------------------------------------------------------------
@router.get("/data-range")
def get_data_range(db: Session = Depends(get_db)) -> dict[str, Any]:
    """
    Database ke logs kis time period ke hain (pehla aur aakhri log).
    hours_span = abhi se pehle log tak kitne ghante. Dashboard ka "All data" option ise use karta hai.
    """
    first, last = db.query(func.min(ApiLog.timestamp), func.max(ApiLog.timestamp)).one()
    if first is None:
        return {"first_log": None, "last_log": None, "hours_span": None}

    first_utc = first if first.tzinfo else first.replace(tzinfo=timezone.utc)
    hours_span = math.ceil((datetime.now(timezone.utc) - first_utc).total_seconds() / 3600) + 1
    return {
        "first_log": first.isoformat(),
        "last_log": last.isoformat(),
        "hours_span": max(hours_span, 1),
    }


# ---------------------------------------------------------------------------
# GET /analytics/services/{service_id}/stats?hours=24
# ---------------------------------------------------------------------------
@router.get("/services/{service_id}/stats")
def get_service_stats(
    service_id: int,
    hours: int = 24,
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Total requests, avg/p95/p99 response time, error rate for a service."""
    _require_service(service_id, db)

    since = _since(hours)
    logs = (
        db.query(ApiLog.status_code, ApiLog.response_time_ms)
        .filter(ApiLog.service_id == service_id, ApiLog.timestamp >= since)
        .all()
    )

    if not logs:
        return _empty_stats(service_id, hours)

    rt_values = sorted(rt for _, rt in logs)
    errors     = sum(1 for sc, _ in logs if sc >= 500)
    total      = len(logs)

    return {
        "service_id":         service_id,
        "hours":              hours,
        "total_requests":     total,
        "avg_response_time_ms": round(_safe_avg(rt_values), 2),
        "p95_response_time_ms": round(_percentile(rt_values, 95), 2),
        "p99_response_time_ms": round(_percentile(rt_values, 99), 2),
        "error_rate":         round(errors / total, 4),
        "error_count":        errors,
    }


def _empty_stats(service_id: int, hours: int) -> dict:
    return {
        "service_id": service_id, "hours": hours,
        "total_requests": 0, "avg_response_time_ms": 0.0,
        "p95_response_time_ms": 0.0, "p99_response_time_ms": 0.0,
        "error_rate": 0.0, "error_count": 0,
    }


# ---------------------------------------------------------------------------
# GET /analytics/health?hours=24
# ---------------------------------------------------------------------------
@router.get("/health")
def get_health(hours: int = 24, db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    """
    Har service ka health status: Healthy / Warning / Critical.
    Pichhle `hours` ghante ka data use hota hai (default 24).
    Thresholds → file ke top par clearly defined constants.
    """
    services = db.query(Service).all()
    since    = _since(hours)
    result   = []

    for svc in services:
        logs = (
            db.query(ApiLog.status_code, ApiLog.response_time_ms)
            .filter(ApiLog.service_id == svc.id, ApiLog.timestamp >= since)
            .all()
        )
        total = len(logs)
        if total == 0:
            result.append({
                "service_id":   svc.id,
                "service_name": svc.name,
                "status":       "Healthy",
                "total_requests": 0,
                "error_rate":   0.0,
                "p95_response_time_ms": 0.0,
                "reason":       f"No traffic in last {hours}h",
            })
            continue

        rt_sorted = sorted(rt for _, rt in logs)
        errors    = sum(1 for sc, _ in logs if sc >= 500)
        error_rate = errors / total
        p95        = _percentile(rt_sorted, 95)

        # Determine status
        if error_rate >= WARNING_ERROR_RATE_MAX or p95 >= WARNING_P95_MAX_MS:
            status = "Critical"
        elif error_rate >= HEALTHY_ERROR_RATE_MAX or p95 >= HEALTHY_P95_MAX_MS:
            status = "Warning"
        else:
            status = "Healthy"

        # Build human-readable reason
        reasons = []
        if error_rate >= WARNING_ERROR_RATE_MAX:
            reasons.append(f"Error rate {error_rate*100:.1f}% >= {WARNING_ERROR_RATE_MAX*100:.0f}%")
        elif error_rate >= HEALTHY_ERROR_RATE_MAX:
            reasons.append(f"Error rate {error_rate*100:.1f}% >= {HEALTHY_ERROR_RATE_MAX*100:.0f}%")
        if p95 >= WARNING_P95_MAX_MS:
            reasons.append(f"p95 {p95:.0f}ms >= {WARNING_P95_MAX_MS}ms")
        elif p95 >= HEALTHY_P95_MAX_MS:
            reasons.append(f"p95 {p95:.0f}ms >= {HEALTHY_P95_MAX_MS}ms")
        if not reasons:
            reasons.append("All metrics within normal range")

        result.append({
            "service_id":           svc.id,
            "service_name":         svc.name,
            "status":               status,
            "total_requests":       total,
            "error_rate":           round(error_rate, 4),
            "p95_response_time_ms": round(p95, 2),
            "reason":               "; ".join(reasons),
        })

    return result


# ---------------------------------------------------------------------------
# GET /analytics/services/{service_id}/endpoints
# ---------------------------------------------------------------------------
@router.get("/services/{service_id}/endpoints")
def get_endpoint_stats(
    service_id: int,
    hours: int = 24,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Per-endpoint stats.
    Sorted: slowest p95 first, most failing first as tiebreaker.
    """
    _require_service(service_id, db)

    since = _since(hours)
    logs  = (
        db.query(ApiLog.endpoint, ApiLog.method, ApiLog.status_code, ApiLog.response_time_ms)
        .filter(ApiLog.service_id == service_id, ApiLog.timestamp >= since)
        .all()
    )

    # Group by (endpoint, method)
    grouped: dict[tuple, list] = {}
    for ep, method, sc, rt in logs:
        key = (ep, method)
        grouped.setdefault(key, []).append((sc, rt))

    stats = []
    for (ep, method), records in grouped.items():
        rt_sorted  = sorted(rt for _, rt in records)
        errors     = sum(1 for sc, _ in records if sc >= 500)
        total      = len(records)
        stats.append({
            "endpoint":             ep,
            "method":               method,
            "total_requests":       total,
            "avg_response_time_ms": round(_safe_avg(rt_sorted), 2),
            "p95_response_time_ms": round(_percentile(rt_sorted, 95), 2),
            "error_count":          errors,
            "error_rate":           round(errors / total, 4),
        })

    # Slowest p95 first, then most failing
    stats.sort(key=lambda x: (-x["p95_response_time_ms"], -x["error_rate"]))
    return stats


# ---------------------------------------------------------------------------
# GET /analytics/services/{service_id}/timeseries
# ---------------------------------------------------------------------------
@router.get("/services/{service_id}/timeseries")
def get_timeseries(
    service_id: int,
    hours: int = 24,
    interval_minutes: int = 60,
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """
    Time-bucketed stats: requests, avg response time, error rate.
    interval_minutes granularity mein data milega.
    """
    _require_service(service_id, db)

    since = _since(hours)
    logs  = (
        db.query(ApiLog.status_code, ApiLog.response_time_ms, ApiLog.timestamp)
        .filter(ApiLog.service_id == service_id, ApiLog.timestamp >= since)
        .all()
    )

    if not logs:
        return []

    # Build buckets
    interval = timedelta(minutes=interval_minutes)
    bucket_count = int(timedelta(hours=hours) / interval) + 1
    buckets: dict[int, list] = {i: [] for i in range(bucket_count)}

    for sc, rt, ts in logs:
        # ts may be naive (SQLite stores without tz)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta     = ts - since
        bucket_i  = int(delta / interval)
        bucket_i  = max(0, min(bucket_i, bucket_count - 1))
        buckets[bucket_i].append((sc, rt))

    result = []
    for i in range(bucket_count):
        bucket_start = since + i * interval
        records      = buckets[i]
        total        = len(records)
        errors       = sum(1 for sc, _ in records if sc >= 500)
        avg_rt       = _safe_avg([rt for _, rt in records])
        result.append({
            "bucket_start":         bucket_start.isoformat(),
            "total_requests":       total,
            "avg_response_time_ms": round(avg_rt, 2),
            "error_rate":           round(errors / total, 4) if total else 0.0,
        })

    return result


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _require_service(service_id: int, db: Session) -> None:
    if not db.get(Service, service_id):
        raise HTTPException(status_code=404, detail=f"Service {service_id} nahi mila")