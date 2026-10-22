from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ServiceCreate(BaseModel):
    name: str
    owner: Optional[str] = None
    description: Optional[str] = None


class ServiceOut(ServiceCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


class LogCreate(BaseModel):
    service_id: int
    caller_service_id: Optional[int] = None
    endpoint: str
    method: str
    status_code: int
    response_time_ms: float


class LogOut(LogCreate):
    model_config = ConfigDict(from_attributes=True)
    id: int
    timestamp: datetime
