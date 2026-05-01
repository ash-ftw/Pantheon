from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import OrganizationTemplate
from app.schemas import TemplateOut
from app.services.presenters import template_to_api

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("", response_model=dict[str, list[TemplateOut]])
def list_templates(db: Session = Depends(get_db)) -> dict:
    templates = db.query(OrganizationTemplate).order_by(OrganizationTemplate.name).all()
    return {"templates": [template_to_api(item) for item in templates]}


@router.get("/{template_id}", response_model=dict[str, TemplateOut])
def get_template(template_id: str, db: Session = Depends(get_db)) -> dict:
    template = db.get(OrganizationTemplate, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"template": template_to_api(template)}
