from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.catalog import DEFENSES
from app.database import get_db
from app.dependencies import can_access_lab, get_current_user
from app.models import Lab, User
from app.schemas import DefenseApply
from app.services.presenters import defense_action_to_api
from app.services.simulation_service import active_defense_actions, apply_defenses

router = APIRouter(tags=["defenses"])


def _load_lab(db: Session, lab_id: str) -> Lab | None:
    return (
        db.query(Lab)
        .options(joinedload(Lab.template), joinedload(Lab.defense_actions))
        .filter(Lab.id == lab_id)
        .first()
    )


@router.get("/labs/{lab_id}/defenses")
def get_lab_defenses(
    lab_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    return {
        "defenses": [defense_action_to_api(item) for item in active_defense_actions(db, lab.id)],
        "catalog": DEFENSES,
    }


@router.post("/labs/{lab_id}/defenses/apply")
def apply_lab_defenses(
    lab_id: str,
    payload: DefenseApply,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    defense_ids = payload.defense_ids or [item for item in [payload.defense_id, payload.catalogId] if item]
    if not defense_ids:
        raise HTTPException(status_code=400, detail="At least one defense_id is required")
    applied = apply_defenses(
        db,
        lab,
        defense_ids,
        simulation_id=payload.simulation_id or payload.simulationId,
        recommendation_id=payload.recommendation_id or payload.recommendationId,
    )
    return {
        "applied": [defense_action_to_api(item) for item in applied],
        "defenses": [defense_action_to_api(item) for item in active_defense_actions(db, lab.id)],
    }
