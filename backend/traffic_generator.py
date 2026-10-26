"""
Traffic Generator for Governance Engine
Chalane ka tarika (backend/ folder se):
    python traffic_generator.py          # normal run
    python traffic_generator.py --reset  # pehle purane logs delete karo
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

# backend/ folder ka path correctly set karo
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine
from models import ApiLog, Base, Service

# ---------------------------------------------------------------------------
# Fixed seed – har baar same data milega
# ---------------------------------------------------------------------------
RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# ---------------------------------------------------------------------------
# Service definitions
# ---------------------------------------------------------------------------
SERVICES = [
    {"name": "login-service",        "owner": "auth-team",      "description": "Handles user authentication & JWT"},
    {"name": "user-service",         "owner": "platform-team",  "description": "User profiles and preferences"},
    {"name": "order-service",        "owner": "commerce-team",  "description": "Order lifecycle management"},
    {"name": "payment-service",      "owner": "finance-team",   "description": "Payment processing & refunds"},
    {"name": "inventory-service",    "owner": "ops-team",       "description": "Stock & warehouse management"},
    {"name": "notification-service", "owner": "platform-team",  "description": "Email, SMS, push notifications"},
]

# caller_service_name -> [callee_service_names]
# login -> user; order -> user, payment, inventory; payment -> notification; order -> notification
CALL_GRAPH = {
    "login-service":   ["user-service"],
    "order-service":   ["user-service", "payment-service", "inventory-service", "notification-service"],
    "payment-service": ["notification-service"],
}

# ---------------------------------------------------------------------------
# Per-service endpoint catalogue
# ---------------------------------------------------------------------------
ENDPOINTS = {
    "login-service": [
        ("/auth/login",   "POST"),
        ("/auth/logout",  "POST"),
        ("/auth/refresh", "POST"),
        ("/auth/verify",  "GET"),
    ],
    "user-service": [
        ("/users",           "GET"),
        ("/users/{id}",      "GET"),
        ("/users/{id}",      "PUT"),
        ("/users/{id}/prefs","GET"),
    ],
    "order-service": [
        ("/orders",          "POST"),
        ("/orders",          "GET"),
        ("/orders/{id}",     "GET"),
        ("/orders/{id}",     "PATCH"),
        ("/orders/{id}/cancel", "POST"),
    ],
    "payment-service": [
        ("/payments/charge",  "POST"),
        ("/payments/refund",  "POST"),
        ("/payments/{id}",    "GET"),
        ("/payments/methods", "GET"),
    ],
    "inventory-service": [
        ("/inventory",          "GET"),
        ("/inventory/{sku}",    "GET"),
        ("/inventory/{sku}",    "PUT"),
        ("/inventory/reserve",  "POST"),
        ("/inventory/release",  "POST"),
    ],
    "notification-service": [
        ("/notify/email", "POST"),
        ("/notify/sms",   "POST"),
        ("/notify/push",  "POST"),
        ("/notify/status","GET"),
    ],
}

# Baseline response time (ms) and std-dev per service
BASELINES = {
    "login-service":        (80,  20),
    "user-service":         (60,  15),
    "order-service":        (120, 30),
    "payment-service":      (150, 35),
    "inventory-service":    (70,  18),
    "notification-service": (90,  25),
}

# Requests per hour per service (rough weight for volume distribution)
RPS_WEIGHT = {
    "login-service":        8,
    "user-service":         20,
    "order-service":        12,
    "payment-service":      10,
    "inventory-service":    8,
    "notification-service": 6,
}

TOTAL_LOGS = 10_000
ERROR_CODES   = [400, 404, 500, 503]
SUCCESS_CODES = [200, 200, 200, 200, 200, 201]  # weighted towards 200
BASE_ERROR_RATE = 0.02

# ---------------------------------------------------------------------------
# Anomaly windows  (all times in UTC)
# ---------------------------------------------------------------------------
NOW_UTC = datetime.now(timezone.utc).replace(second=0, microsecond=0)

def _window(days_ago_start: float, minutes: int = 30):
    """Returns (start, end) datetime tuple."""
    start = NOW_UTC - timedelta(days=days_ago_start)
    return start, start + timedelta(minutes=minutes)

# (a) payment-service latency spike – two separate 30-min windows
PAYMENT_SPIKE_1 = _window(5.5)    # ~5.5 days ago
PAYMENT_SPIKE_2 = _window(1.8)    # ~1.8 days ago

# (b) inventory-service error rate spike (40%+) – one 30-min window
INVENTORY_ERROR_SPIKE = _window(3.2)

# (c) order-service slow response – one 30-min window
ORDER_SLOW_WINDOW = _window(2.1)

INJECTED_WINDOWS = [
    ("payment-service",   PAYMENT_SPIKE_1),
    ("payment-service",   PAYMENT_SPIKE_2),
    ("inventory-service", INVENTORY_ERROR_SPIKE),
    ("order-service",     ORDER_SLOW_WINDOW),
]

ANOMALY_GROUND_TRUTH = {
    "payment_latency_spike_1": {
        "service": "payment-service",
        "type": "latency_spike",
        "start_utc": PAYMENT_SPIKE_1[0].isoformat(),
        "end_utc":   PAYMENT_SPIKE_1[1].isoformat(),
        "description": "Avg response time spiked to ~800ms (5x baseline)",
    },
    "payment_latency_spike_2": {
        "service": "payment-service",
        "type": "latency_spike",
        "start_utc": PAYMENT_SPIKE_2[0].isoformat(),
        "end_utc":   PAYMENT_SPIKE_2[1].isoformat(),
        "description": "Avg response time spiked to ~900ms (6x baseline)",
    },
    "inventory_error_spike": {
        "service": "inventory-service",
        "type": "error_rate_spike",
        "start_utc": INVENTORY_ERROR_SPIKE[0].isoformat(),
        "end_utc":   INVENTORY_ERROR_SPIKE[1].isoformat(),
        "description": "Error rate jumped to ~45% (normal ~2%)",
    },
    "order_slow_response": {
        "service": "order-service",
        "type": "slow_response",
        "start_utc": ORDER_SLOW_WINDOW[0].isoformat(),
        "end_utc":   ORDER_SLOW_WINDOW[1].isoformat(),
        "description": "Avg response time spiked to ~600ms (5x baseline)",
    },
}


def in_window(ts: datetime, window: tuple) -> bool:
    return window[0] <= ts <= window[1]


# ---------------------------------------------------------------------------
# Helper: generate a single log row dict
# ---------------------------------------------------------------------------
def make_log(service_name: str, service_id: int, caller_id, ts: datetime) -> dict:
    endpoint, method = random.choice(ENDPOINTS[service_name])
    base_ms, std_ms = BASELINES[service_name]

    # --- Inject anomalies ---
    error_rate = BASE_ERROR_RATE
    response_time_ms = max(5, random.gauss(base_ms, std_ms))

    if service_name == "payment-service":
        if in_window(ts, PAYMENT_SPIKE_1):
            response_time_ms = max(400, random.gauss(800, 100))
        elif in_window(ts, PAYMENT_SPIKE_2):
            response_time_ms = max(500, random.gauss(900, 120))

    if service_name == "inventory-service" and in_window(ts, INVENTORY_ERROR_SPIKE):
        error_rate = 0.45

    if service_name == "order-service" and in_window(ts, ORDER_SLOW_WINDOW):
        response_time_ms = max(300, random.gauss(600, 80))

    # --- Pick status code ---
    if random.random() < error_rate:
        if service_name == "inventory-service" and in_window(ts, INVENTORY_ERROR_SPIKE):
            status_code = random.choice([500, 503])
        else:
            status_code = random.choice(ERROR_CODES)
    else:
        status_code = random.choice(SUCCESS_CODES)

    return {
        "service_id":      service_id,
        "caller_service_id": caller_id,
        "endpoint":        endpoint,
        "method":          method,
        "status_code":     status_code,
        "response_time_ms": round(response_time_ms, 2),
        "timestamp":       ts,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def seed_demo_data(reset: bool = False):
    """Create the default service topology and traffic if the DB is empty or stale."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        existing_services = db.query(Service).count()
        existing_logs = db.query(ApiLog).count()
        should_reset = reset or existing_services < len(SERVICES) or existing_logs < 5000

        if should_reset:
            db.query(ApiLog).delete()
            db.query(Service).delete()
            db.commit()

        service_ids: dict[str, int] = {}
        for svc in SERVICES:
            existing = db.query(Service).filter_by(name=svc["name"]).first()
            if existing:
                service_ids[svc["name"]] = existing.id
            else:
                obj = Service(**svc)
                db.add(obj)
                db.flush()
                service_ids[svc["name"]] = obj.id
        db.commit()

        if should_reset:
            weighted_services = []
            for svc_name, weight in RPS_WEIGHT.items():
                callees = CALL_GRAPH.get(svc_name, [])
                for _ in range(weight):
                    weighted_services.append((svc_name, callees))

            start_time = NOW_UTC - timedelta(days=7)
            total_seconds = int(timedelta(days=7).total_seconds())

            batch = []
            for _ in range(TOTAL_LOGS):
                svc_name, _ = random.choice(weighted_services)
                svc_id = service_ids[svc_name]
                caller_id = None
                for caller_svc, callee_list in CALL_GRAPH.items():
                    if svc_name in callee_list and random.random() < 0.7:
                        caller_id = service_ids[caller_svc]
                        break

                offset_s = random.randint(0, total_seconds)
                ts = start_time + timedelta(seconds=offset_s)
                batch.append(ApiLog(**make_log(svc_name, svc_id, caller_id, ts)))

                if len(batch) >= 500:
                    db.bulk_save_objects(batch)
                    db.commit()
                    batch.clear()

            if batch:
                db.bulk_save_objects(batch)
                db.commit()
                batch.clear()

            for svc_name, (w_start, w_end) in INJECTED_WINDOWS:
                svc_id = service_ids[svc_name]
                w_seconds = int((w_end - w_start).total_seconds())
                for _ in range(45):
                    offset_s = random.randint(0, w_seconds)
                    ts = w_start + timedelta(seconds=offset_s)
                    caller_id = None
                    for caller_svc, callee_list in CALL_GRAPH.items():
                        if svc_name in callee_list and random.random() < 0.7:
                            caller_id = service_ids[caller_svc]
                            break
                    batch.append(ApiLog(**make_log(svc_name, svc_id, caller_id, ts)))

            if batch:
                db.bulk_save_objects(batch)
                db.commit()
                batch.clear()

        gt_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "anomaly_ground_truth.json")
        with open(gt_path, "w") as f:
            json.dump(ANOMALY_GROUND_TRUTH, f, indent=2)
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Generate fake API traffic logs")
    parser.add_argument("--reset", action="store_true", help="Pehle purane logs delete karo")
    args = parser.parse_args()
    seed_demo_data(reset=args.reset)


if __name__ == "__main__":
    main()
