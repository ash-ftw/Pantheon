from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AttackScenario
from app.schemas import ScenarioOut
from app.services.presenters import scenario_to_api

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


@router.get("", response_model=dict[str, list[ScenarioOut]])
def list_scenarios(db: Session = Depends(get_db)) -> dict:
    scenarios = db.query(AttackScenario).order_by(AttackScenario.scenario_name).all()
    return {"scenarios": [scenario_to_api(item) for item in scenarios]}


@router.get("/{scenario_id}", response_model=dict[str, ScenarioOut])
def get_scenario(scenario_id: str, db: Session = Depends(get_db)) -> dict:
    scenario = db.get(AttackScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"scenario": scenario_to_api(scenario)}
