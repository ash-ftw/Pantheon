from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.dependencies import can_access_lab, get_current_user
from app.models import Lab, OrganizationTemplate, ServiceInstance, TargetApplication, User
from app.schemas import LabCreate, LabOut
from app.services.kubernetes_service import KubernetesProvisioningError, KubernetesService
from app.services.presenters import lab_to_api

router = APIRouter(prefix="/labs", tags=["labs"])


def _load_lab(db: Session, lab_id: str) -> Lab | None:
    return (
        db.query(Lab)
        .options(joinedload(Lab.template), joinedload(Lab.services), joinedload(Lab.target_applications))
        .filter(Lab.id == lab_id)
        .first()
    )


def _namespace_for_lab(lab_id: str) -> str:
    return f"{settings.namespace_prefix}-{lab_id[:8]}"


@router.post("", response_model=dict[str, LabOut], status_code=status.HTTP_201_CREATED)
def create_lab(payload: LabCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    template_id = payload.template_id or payload.templateId or "small-company"
    template = db.get(OrganizationTemplate, template_id)
    if not template:
        raise HTTPException(status_code=400, detail="Unknown organization template")

    lab = Lab(
        user_id=user.id,
        template_id=template.id,
        lab_name=payload.lab_name or payload.labName or f"{template.name} Lab",
        namespace="pending",
        status="Provisioning",
        deployment_mode=settings.kubernetes_mode,
    )
    db.add(lab)
    db.flush()
    lab.namespace = _namespace_for_lab(lab.id)
    db.commit()
    db.refresh(lab)

    service_definitions = template.service_config_json.get("services", [])
    k8s = KubernetesService()
    try:
        k8s.create_lab(lab.namespace, service_definitions)
        lab.status = "Running"
        lab.error_message = None
        _ensure_service_instances(db, lab, service_definitions, "Running")
    except KubernetesProvisioningError as exc:
        lab.status = "Failed"
        lab.error_message = str(exc)
    db.commit()

    loaded = _load_lab(db, lab.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Lab was created but could not be loaded")
    return {"lab": lab_to_api(loaded)}


@router.get("", response_model=dict[str, list[LabOut]])
def list_labs(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    query = (
        db.query(Lab)
        .options(joinedload(Lab.template), joinedload(Lab.services), joinedload(Lab.target_applications))
        .order_by(Lab.created_at.desc())
    )
    if user.role not in {"Admin", "Instructor"}:
        query = query.filter(Lab.user_id == user.id)
    return {"labs": [lab_to_api(item) for item in query.all()]}


@router.get("/{lab_id}", response_model=dict[str, LabOut])
def get_lab(lab_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    return {"lab": lab_to_api(lab)}


@router.get("/{lab_id}/kubernetes-status")
def get_kubernetes_status(
    lab_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    try:
        status_payload = KubernetesService().get_lab_status(lab.namespace, _service_definitions_for_lab(lab))
        status_payload["labId"] = lab.id
        _apply_kubernetes_status(lab, status_payload)
        lab.error_message = None
    except KubernetesProvisioningError as exc:
        lab.status = "Failed"
        lab.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    db.commit()
    loaded = _load_lab(db, lab.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Lab status was refreshed but could not be loaded")
    return {"kubernetesStatus": status_payload, "lab": lab_to_api(loaded)}


@router.delete("/{lab_id}", response_model=dict[str, LabOut])
def delete_lab(lab_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")

    try:
        KubernetesService().delete_lab(lab.namespace)
        lab.status = "Deleted"
        lab.deleted_at = datetime.now(timezone.utc)
        for service in lab.services:
            service.status = "Deleted"
    except KubernetesProvisioningError as exc:
        lab.status = "Failed"
        lab.error_message = str(exc)
    db.commit()
    loaded = _load_lab(db, lab.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Lab was deleted but could not be loaded")
    return {"lab": lab_to_api(loaded)}


@router.post("/{lab_id}/start", response_model=dict[str, LabOut])
def start_lab(lab_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return _scale_lab(lab_id, 1, db, user)


@router.post("/{lab_id}/stop", response_model=dict[str, LabOut])
def stop_lab(lab_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return _scale_lab(lab_id, 0, db, user)


def _scale_lab(lab_id: str, replicas: int, db: Session, user: User) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    service_defs = _service_definitions_for_lab(lab)
    k8s = KubernetesService()
    try:
        if replicas == 1 and settings.kubernetes_mode == "real":
            k8s.create_lab(lab.namespace, service_defs)
            _ensure_service_instances(db, lab, service_defs, "Running")
        else:
            k8s.set_lab_scale(lab.namespace, service_defs, replicas)
        lab.status = "Running" if replicas else "Stopped"
        lab.deployment_mode = settings.kubernetes_mode
        lab.error_message = None
        for service in lab.services:
            service.status = lab.status
    except KubernetesProvisioningError as exc:
        lab.status = "Failed"
        lab.error_message = str(exc)
    db.commit()
    loaded = _load_lab(db, lab.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Lab was scaled but could not be loaded")
    return {"lab": lab_to_api(loaded)}


def _service_definitions_for_lab(lab: Lab) -> list[dict]:
    target_by_service = {target.service_name: target for target in lab.target_applications}
    if lab.services:
        definitions: list[dict] = []
        for item in lab.services:
            definition = {
                "name": item.service_name,
                "type": item.service_type,
                "port": item.port,
                "exposed": item.exposed,
            }
            target = target_by_service.get(item.service_name)
            if target:
                definition.update(
                    {
                        "image": target.image,
                        "import_type": target.import_type,
                        "health_path": target.health_path,
                        "manifest": target.manifest_json.get("manifest"),
                        "local_url": target.manifest_json.get("local_url"),
                        "normal_paths": target.manifest_json.get("normal_paths", []),
                    }
                )
            definitions.append(definition)
        return definitions
    return lab.template.service_config_json.get("services", [])


def _ensure_service_instances(db: Session, lab: Lab, service_definitions: list[dict], status: str) -> None:
    existing = {item.service_name: item for item in lab.services}
    for service in service_definitions:
        instance = existing.get(service["name"])
        if instance:
            instance.service_type = service["type"]
            instance.kubernetes_deployment_name = service["name"]
            instance.kubernetes_service_name = service["name"]
            instance.status = status
            instance.port = service.get("port")
            instance.exposed = bool(service.get("exposed"))
            continue
        db.add(
            ServiceInstance(
                lab_id=lab.id,
                service_name=service["name"],
                service_type=service["type"],
                kubernetes_deployment_name=service["name"],
                kubernetes_service_name=service["name"],
                status=status,
                port=service.get("port"),
                exposed=bool(service.get("exposed")),
            )
        )


def _apply_kubernetes_status(lab: Lab, status_payload: dict) -> None:
    by_name = {item["name"]: item for item in status_payload.get("services", [])}
    for service in lab.services:
        service_status = by_name.get(service.service_name)
        if service_status:
            service.status = service_status.get("status", service.status)
    for target in lab.target_applications:
        service_status = by_name.get(target.service_name)
        if service_status:
            target.status = service_status.get("status", target.status)
    summary = status_payload.get("summary", {})
    if summary.get("failedServices", 0) > 0:
        lab.status = "Failed"
        return
    if summary.get("allReady"):
        lab.status = "Running"
        return
    if lab.status not in {"Stopped", "Deleted"}:
        lab.status = "Provisioning"
