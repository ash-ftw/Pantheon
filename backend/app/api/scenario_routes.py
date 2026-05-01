from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import can_access_lab, get_current_user
from app.models import AttackScenario, Lab, User
from app.schemas import ScenarioOut
from app.services.presenters import scenario_to_api

router = APIRouter(prefix="/scenarios", tags=["scenarios"])


def _accessible_lab_ids(db: Session, user: User) -> set[str]:
    query = db.query(Lab.id)
    if user.role not in {"Admin", "Instructor"}:
        query = query.filter(Lab.user_id == user.id)
    return {row[0] for row in query.all()}


def _can_view_scenario(scenario: AttackScenario, accessible_labs: set[str]) -> bool:
    custom_lab_id = scenario.scenario_config_json.get("custom_lab_id")
    return not custom_lab_id or custom_lab_id in accessible_labs


@router.get("", response_model=dict[str, list[ScenarioOut]])
def list_scenarios(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    accessible_labs = _accessible_lab_ids(db, user)
    scenarios = db.query(AttackScenario).order_by(AttackScenario.scenario_name).all()
    visible = [item for item in scenarios if _can_view_scenario(item, accessible_labs)]
    return {"scenarios": [scenario_to_api(item) for item in visible]}


@router.get("/{scenario_id}", response_model=dict[str, ScenarioOut])
def get_scenario(
    scenario_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    scenario = db.get(AttackScenario, scenario_id)
    if not scenario or not _can_view_scenario(scenario, _accessible_lab_ids(db, user)):
        raise HTTPException(status_code=404, detail="Scenario not found")
    return {"scenario": scenario_to_api(scenario)}
