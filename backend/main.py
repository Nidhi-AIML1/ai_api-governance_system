from typing import List, Optional
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from database import engine, get_db
import analytics  # Phase 2 – analytics router
import graph      # Phase 3 – dependency graph router
import ml_routes  # Phase 4 – ML anomaly detection router
from traffic_generator import seed_demo_data

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="AI-Powered API & Microservice Governance Engine")


@app.on_event("startup")
def ensure_seed_data():
    seed_demo_data(reset=False)

# Phase 2 – analytics endpoints
app.include_router(analytics.router)

# Phase 3 – dependency graph endpoints
app.include_router(graph.router)

# Phase 4 – ML anomaly detection endpoints
app.include_router(ml_routes.router)


@app.get("/")
def home():
    return {"message": "Governance Engine is running"}


# ---------- Services ----------
@app.post("/services", response_model=schemas.ServiceOut)
def create_service(data: schemas.ServiceCreate, db: Session = Depends(get_db)):
    if db.query(models.Service).filter_by(name=data.name).first():
        raise HTTPException(status_code=400, detail="Service already exists")
    service = models.Service(**data.model_dump())
    db.add(service)
    db.commit()
    db.refresh(service)
    return service


@app.get("/services", response_model=List[schemas.ServiceOut])
def list_services(db: Session = Depends(get_db)):
    return db.query(models.Service).all()


# ---------- Logs ----------
@app.post("/logs", response_model=schemas.LogOut)
def create_log(data: schemas.LogCreate, db: Session = Depends(get_db)):
    if not db.get(models.Service, data.service_id):
        raise HTTPException(status_code=404, detail="Service not found")
    if data.caller_service_id is not None and not db.get(models.Service, data.caller_service_id):
        raise HTTPException(status_code=404, detail="Caller service not found")
    log = models.ApiLog(**data.model_dump())
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@app.get("/logs", response_model=List[schemas.LogOut])
def list_logs(service_id: Optional[int] = None, limit: int = 100, db: Session = Depends(get_db)):
    q = db.query(models.ApiLog)
    if service_id:
        q = q.filter(models.ApiLog.service_id == service_id)
    return q.order_by(models.ApiLog.timestamp.desc()).limit(limit).all()

import ai_routes
app.include_router(ai_routes.router)

import governance_routes
app.include_router(governance_routes.router)