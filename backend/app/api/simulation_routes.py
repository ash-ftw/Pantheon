from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import can_access_lab, get_current_user
from app.models import AIAnalysis, AttackScenario, DefenseRecommendation, Lab, SimulationRun, User
from app.schemas import SimulationCreate
from app.services.presenters import analysis_to_api, log_to_api, recommendation_to_api, simulation_to_api
from app.services.simulation_service import run_simulation

router = APIRouter(tags=["simulations"])


def _load_lab(db: Session, lab_id: str) -> Lab | None:
    return (
        db.query(Lab)
        .options(joinedload(Lab.template), joinedload(Lab.services), joinedload(Lab.defense_actions))
        .filter(Lab.id == lab_id)
        .first()
    )


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


@router.post("/labs/{lab_id}/simulations", status_code=status.HTTP_201_CREATED)
def create_simulation(
    lab_id: str,
    payload: SimulationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    if lab.status != "Running":
        raise HTTPException(status_code=409, detail="Lab must be running before simulation")
    scenario_id = payload.scenario_id or payload.scenarioId
    if not scenario_id:
        raise HTTPException(status_code=400, detail="scenario_id is required")
    scenario = db.get(AttackScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=400, detail="Unknown scenario")
    if lab.template_id not in scenario.scenario_config_json.get("allowed_template_ids", []):
        raise HTTPException(status_code=400, detail="Scenario is not compatible with this lab template")

    simulation = run_simulation(db, lab, scenario)
    loaded = _load_simulation(db, simulation.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Simulation was created but could not be loaded")
    return {"simulation": simulation_to_api(loaded)}


@router.get("/simulations/{simulation_id}")
def get_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    simulation = _load_simulation(db, simulation_id)
    if not simulation or not can_access_lab(user, simulation.lab.user_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    return {"simulation": simulation_to_api(simulation)}


@router.post("/simulations/{simulation_id}/stop")
def stop_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    simulation = _load_simulation(db, simulation_id)
    if not simulation or not can_access_lab(user, simulation.lab.user_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    simulation.status = "Stopped"
    db.commit()
    loaded = _load_simulation(db, simulation_id)
    return {"simulation": simulation_to_api(loaded)}


@router.get("/simulations/{simulation_id}/logs")
def get_simulation_logs(
    simulation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    simulation = _load_simulation(db, simulation_id)
    if not simulation or not can_access_lab(user, simulation.lab.user_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    return {"logs": [log_to_api(item) for item in simulation.logs]}


@router.get("/labs/{lab_id}/logs")
def get_lab_logs(
    lab_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    simulations = (
        db.query(SimulationRun)
        .options(joinedload(SimulationRun.logs))
        .filter(SimulationRun.lab_id == lab.id)
        .order_by(SimulationRun.started_at)
        .all()
    )
    return {"logs": [log_to_api(log) for simulation in simulations for log in simulation.logs]}


@router.post("/simulations/{simulation_id}/analyze")
def analyze_simulation(
    simulation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    simulation = _load_simulation(db, simulation_id)
    if not simulation or not can_access_lab(user, simulation.lab.user_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    return {"analysis": analysis_to_api(simulation.ai_analysis)}


@router.get("/simulations/{simulation_id}/analysis")
def get_analysis(
    simulation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    simulation = _load_simulation(db, simulation_id)
    if not simulation or not can_access_lab(user, simulation.lab.user_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    analysis: AIAnalysis | None = simulation.ai_analysis
    return {"analysis": analysis_to_api(analysis)}


@router.get("/simulations/{simulation_id}/recommendations")
def get_recommendations(
    simulation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    simulation = _load_simulation(db, simulation_id)
    if not simulation or not can_access_lab(user, simulation.lab.user_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    recommendations: list[DefenseRecommendation] = simulation.recommendations
    return {"recommendations": [recommendation_to_api(item) for item in recommendations]}
