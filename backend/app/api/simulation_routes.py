from __future__ import annotations

import asyncio
from queue import Empty, Queue
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session, joinedload

from app.database import SessionLocal, get_db
from app.dependencies import can_access_lab, get_current_user
from app.models import AIAnalysis, AttackScenario, DefenseRecommendation, Lab, SimulationJob, SimulationRun, User, utcnow
from app.schemas import SimulationCreate
from app.security import decode_access_token
from app.services.kubernetes_service import KubernetesService, KubernetesProvisioningError
from app.services.presenters import analysis_to_api, log_to_api, recommendation_to_api, simulation_job_to_api, simulation_to_api
from app.services.simulation_service import mark_simulation_jobs_cancelled, run_simulation, service_definitions_for_lab

router = APIRouter(tags=["simulations"])


def _load_lab(db: Session, lab_id: str) -> Lab | None:
    return (
        db.query(Lab)
        .options(
            joinedload(Lab.template),
            joinedload(Lab.services),
            joinedload(Lab.target_applications),
            joinedload(Lab.defense_actions),
        )
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
            joinedload(SimulationRun.jobs),
            joinedload(SimulationRun.ai_analysis),
            joinedload(SimulationRun.recommendations),
            joinedload(SimulationRun.report),
        )
        .filter(SimulationRun.id == simulation_id)
        .first()
    )


def _validate_scenario_for_lab(lab: Lab, scenario: AttackScenario) -> None:
    config = scenario.scenario_config_json
    custom_lab_id = config.get("custom_lab_id")
    if custom_lab_id:
        if custom_lab_id != lab.id:
            raise HTTPException(status_code=400, detail="Custom scenario belongs to a different lab")
    elif lab.template_id not in config.get("allowed_template_ids", []):
        raise HTTPException(status_code=400, detail="Scenario is not compatible with this lab template")

    service_names = {service["name"] for service in service_definitions_for_lab(lab)}
    for step in config.get("steps", []):
        target = step.get("target")
        if custom_lab_id and target not in service_names:
            raise HTTPException(status_code=400, detail="Custom scenario target is outside this lab")


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
    _validate_scenario_for_lab(lab, scenario)

    simulation = run_simulation(db, lab, scenario)
    loaded = _load_simulation(db, simulation.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Simulation was created but could not be loaded")
    return {"simulation": simulation_to_api(loaded)}


@router.websocket("/labs/{lab_id}/simulations/stream")
async def stream_simulation(websocket: WebSocket, lab_id: str) -> None:
    await websocket.accept()
    token = websocket.query_params.get("token", "")
    scenario_id = websocket.query_params.get("scenario_id") or websocket.query_params.get("scenarioId")
    if not token or not scenario_id:
        await websocket.send_json({"type": "simulation_error", "detail": "token and scenario_id are required"})
        await websocket.close(code=1008)
        return

    events: Queue[dict[str, Any]] = Queue()
    task = asyncio.create_task(asyncio.to_thread(_run_streamed_simulation, lab_id, scenario_id, token, events))
    try:
        while True:
            while True:
                try:
                    await websocket.send_json(jsonable_encoder(events.get_nowait()))
                except Empty:
                    break
            if task.done():
                break
            await asyncio.sleep(0.1)
        simulation = await task
        while True:
            try:
                await websocket.send_json(jsonable_encoder(events.get_nowait()))
            except Empty:
                break
        await websocket.send_json(jsonable_encoder({"type": "simulation_completed", "simulation": simulation}))
        await websocket.close(code=1000)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        await websocket.send_json({"type": "simulation_error", "detail": str(exc)})
        await websocket.close(code=1011)


def _run_streamed_simulation(
    lab_id: str,
    scenario_id: str,
    token: str,
    events: Queue[dict[str, Any]],
) -> dict:
    user_id = decode_access_token(token)
    if not user_id:
        raise ValueError("Invalid or expired token")
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        lab = _load_lab(db, lab_id)
        if not lab or not can_access_lab(user, lab.user_id):
            raise ValueError("Lab not found")
        if lab.status != "Running":
            raise ValueError("Lab must be running before simulation")
        scenario = db.get(AttackScenario, scenario_id)
        if not scenario:
            raise ValueError("Unknown scenario")
        _validate_scenario_for_lab(lab, scenario)
        events.put({"type": "simulation_stream_connected", "labId": lab.id, "scenarioId": scenario.id})
        simulation = run_simulation(db, lab, scenario, progress_callback=events.put)
        loaded = _load_simulation(db, simulation.id)
        if not loaded:
            raise ValueError("Simulation was created but could not be loaded")
        return simulation_to_api(loaded)


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
    if simulation.status in {"Completed", "Failed", "Stopped"}:
        return {"simulation": simulation_to_api(simulation)}
    simulation.status = "Stopping"
    simulation.completed_at = utcnow()
    simulation.result_summary = "Simulation cancellation requested. Active Kubernetes jobs are being stopped."
    try:
        KubernetesService().cancel_simulation_jobs(simulation.lab.namespace, simulation.id)
    except KubernetesProvisioningError as exc:
        simulation.status = "Failed"
        simulation.result_summary = f"Simulation cancellation failed: {exc}"
        db.commit()
        loaded = _load_simulation(db, simulation_id)
        return {"simulation": simulation_to_api(loaded)}
    mark_simulation_jobs_cancelled(db, simulation.id)
    simulation.status = "Stopped"
    simulation.result_summary = "Simulation was stopped and active Kubernetes jobs were cancelled."
    db.commit()
    loaded = _load_simulation(db, simulation_id)
    return {"simulation": simulation_to_api(loaded)}


@router.get("/simulations/{simulation_id}/jobs")
def get_simulation_jobs(
    simulation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    simulation = _load_simulation(db, simulation_id)
    if not simulation or not can_access_lab(user, simulation.lab.user_id):
        raise HTTPException(status_code=404, detail="Simulation not found")
    jobs = (
        db.query(SimulationJob)
        .filter(SimulationJob.simulation_id == simulation.id)
        .order_by(SimulationJob.created_at)
        .all()
    )
    return {"jobs": [simulation_job_to_api(item) for item in jobs]}


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
