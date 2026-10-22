from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from database import Base


def utcnow():
    return datetime.now(timezone.utc)


class Service(Base):
    __tablename__ = "services"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    owner = Column(String)
    description = Column(String)
    created_at = Column(DateTime, default=utcnow)


class ApiLog(Base):
    __tablename__ = "api_logs"
    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False, index=True)
    # Phase 3 (dependency graph) mein ye kaam aayega: kaun kisko call kar raha hai
    caller_service_id = Column(Integer, ForeignKey("services.id"), nullable=True)
    endpoint = Column(String, nullable=False)
    method = Column(String, nullable=False)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=utcnow, index=True)


class Anomaly(Base):
    __tablename__ = "anomalies"
    id = Column(Integer, primary_key=True, index=True)
    service_id = Column(Integer, ForeignKey("services.id"), nullable=False, index=True)
    window_start = Column(DateTime, nullable=False, index=True)
    window_end = Column(DateTime, nullable=False)
    score = Column(Float, nullable=False)
    avg_response_ms = Column(Float, nullable=False)
    error_rate = Column(Float, nullable=False)
    detected_at = Column(DateTime, default=utcnow)

