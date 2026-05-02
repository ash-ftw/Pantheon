from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Lab, User
from app.services.kubernetes_service import KubernetesProvisioningError, KubernetesService
from app.services.presenters import lab_to_api
from app.services.simulation_service import service_definitions_for_lab

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: User) -> None:
    if user.role != "Admin":
        raise HTTPException(status_code=403, detail="Admin role required")


def _load_lab(db: Session, lab_id: str) -> Lab | None:
    return (
        db.query(Lab)
        .options(
            joinedload(Lab.owner),
            joinedload(Lab.template),
            joinedload(Lab.services),
            joinedload(Lab.target_applications),
            joinedload(Lab.defense_actions),
            joinedload(Lab.simulations),
        )
        .filter(Lab.id == lab_id)
        .first()
    )


@router.get("/labs")
def list_admin_labs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _require_admin(user)
    labs = (
        db.query(Lab)
        .options(
            joinedload(Lab.owner),
            joinedload(Lab.template),
            joinedload(Lab.services),
            joinedload(Lab.target_applications),
            joinedload(Lab.defense_actions),
            joinedload(Lab.simulations),
        )
        .order_by(Lab.created_at.desc())
        .all()
    )
    return {"labs": [_admin_lab_record(lab) for lab in labs]}


@router.post("/labs/{lab_id}/status")
def refresh_admin_lab_status(
    lab_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _require_admin(user)
    lab = _load_lab(db, lab_id)
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    try:
        status_payload = KubernetesService().get_lab_status(lab.namespace, service_definitions_for_lab(lab))
        service_status_by_name = {item["name"]: item for item in status_payload.get("services", [])}
        for service in lab.services:
            service_status = service_status_by_name.get(service.service_name)
            if service_status:
                service.status = service_status.get("status", service.status)
        summary = status_payload.get("summary", {})
        lab.status = "Running" if summary.get("allReady") else "Provisioning"
        lab.error_message = None
    except KubernetesProvisioningError as exc:
        lab.status = "Failed"
        lab.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    loaded = _load_lab(db, lab_id)
    return {"kubernetesStatus": status_payload, "lab": _admin_lab_record(loaded or lab)}


@router.post("/labs/{lab_id}/cleanup")
def cleanup_admin_lab(
    lab_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _require_admin(user)
    lab = _load_lab(db, lab_id)
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    try:
        KubernetesService().delete_lab(lab.namespace)
        lab.status = "Deleted"
        lab.deleted_at = datetime.now(timezone.utc)
        lab.error_message = None
        for service in lab.services:
            service.status = "Deleted"
        for target in lab.target_applications:
            target.status = "Deleted"
    except KubernetesProvisioningError as exc:
        lab.status = "Failed"
        lab.error_message = str(exc)
    db.commit()
    loaded = _load_lab(db, lab_id)
    return {"lab": _admin_lab_record(loaded or lab)}


def _admin_lab_record(lab: Lab) -> dict:
    payload = lab_to_api(lab)
    payload["owner"] = {
        "id": lab.owner.id,
        "name": lab.owner.name,
        "email": lab.owner.email,
        "role": lab.owner.role,
    }
    payload["namespaceStatus"] = {
        "namespace": lab.namespace,
        "status": lab.status,
        "errorMessage": lab.error_message,
        "serviceCount": len(lab.services),
        "targetApplicationCount": len(lab.target_applications),
    }
    return payload
