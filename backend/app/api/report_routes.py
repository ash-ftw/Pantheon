from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import can_access_lab, get_current_user
from app.models import Lab, Report, SimulationRun, User
from app.services.presenters import report_to_api
from app.services.simulation_service import create_report

router = APIRouter(tags=["reports"])


def _load_simulation(db: Session, simulation_id: str) -> SimulationRun | None:
    return (
        db.query(SimulationRun)
        .options(
            joinedload(SimulationRun.lab).joinedload(Lab.template),
            joinedload(SimulationRun.scenario),
            joinedload(SimulationRun.logs),
            joinedload(SimulationRun.ai_analysis),
            joinedload(SimulationRun.recommendations),
            joinedload(SimulationRun.report),
        )
        .filter(SimulationRun.id == simulation_id)
        .first()
    )


@router.post("/simulations/{simulation_id}/report", status_code=status.HTTP_201_CREATED)
def generate_report(
    simulation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    simulation = _load_simulation(db, simulation_id)
    if not simulation or not can_access_lab(user, simulation.lab.user_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    report = create_report(db, simulation)
    return {"report": report_to_api(report)}


@router.get("/reports/{report_id}")
def get_report(
    report_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    report = (
        db.query(Report)
        .options(joinedload(Report.simulation).joinedload(SimulationRun.lab))
        .filter(Report.id == report_id)
        .first()
    )
    if not report or not can_access_lab(user, report.simulation.lab.user_id):
        raise HTTPException(status_code=404, detail="Report not found")
    return {"report": report_to_api(report)}


@router.get("/labs/{lab_id}/reports")
def get_lab_reports(
    lab_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    lab = db.get(Lab, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    reports = db.query(Report).filter(Report.lab_id == lab.id).order_by(Report.created_at.desc()).all()
    return {"reports": [report_to_api(item) for item in reports]}
