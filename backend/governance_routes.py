"""API Governance endpoints: /governance/..."""
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import governance as gov
from database import get_db

router = APIRouter(prefix="/governance", tags=["governance"])

# Server start hote hi autonomous scan ka timer chalu (GOVERNANCE_AUTOSCAN=0 se band hota hai)
gov.start_autoscan()


@router.get("/status")
def status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Setup hua ya nahi, autonomous scan chal raha hai ya nahi, aakhri scan kab hua."""
    last = gov.list_scans(db, 1)
    return {
        "setup": gov.is_setup(db),
        "auto_scan_enabled": gov.autoscan_enabled(),
        "auto_scan_minutes": gov.scan_interval_minutes(),
        "last_scan_at": last[0]["created_at"] if last else None,
        "last_scan_trigger": last[0]["trigger"] if last else None,
    }


@router.get("/report")
def report(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Sabse naya scan report. Setup ho gaya ho aur koi scan na ho to ek scan chala deta hai."""
    setup = gov.is_setup(db)
    scan = gov.latest_scan(db)
    if scan is None and setup:
        scan = gov.run_scan(db, trigger="auto")
    return {"setup": setup, "scan": scan}


@router.post("/scan")
def scan_now(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Abhi ek scan chalao."""
    return gov.run_scan(db, trigger="manual")


@router.get("/scans")
def scans(limit: int = 10, db: Session = Depends(get_db)) -> List[Dict[str, Any]]:
    """Purane scans ki history (score aur findings ki ginti)."""
    return gov.list_scans(db, limit)


@router.post("/seed-demo")
def seed_demo(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Demo ke liye API catalog, documented architecture aur kuch extra (nakli) traffic banata hai, phir scan chalata hai."""
    try:
        info = gov.seed_demo(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    scan = gov.run_scan(db, trigger="manual")
    return {"seeded": info, "summary": scan["summary"]}


@router.delete("/seed-demo")
def remove_demo(db: Session = Depends(get_db)) -> Dict[str, int]:
    """Demo data hata deta hai (extra traffic, catalog, documented architecture, scans)."""
    return gov.remove_demo(db)