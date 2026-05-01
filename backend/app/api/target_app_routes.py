from __future__ import annotations

import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.dependencies import can_access_lab, get_current_user
from app.models import AttackScenario, Lab, ServiceInstance, TargetApplication, User
from app.schemas import CustomScenarioCreate, ScenarioOut, TargetApplicationCreate, TargetApplicationOut
from app.services.kubernetes_service import KubernetesProvisioningError, KubernetesService
from app.services.presenters import lab_to_api, scenario_to_api, target_application_to_api
from app.services.simulation_service import service_definitions_for_lab

router = APIRouter(tags=["target-applications"])

_SERVICE_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_ALLOWED_IMPORT_TYPES = {"docker-image", "kubernetes-yaml", "local-service"}
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
_ALLOWED_RISKS = {"Low", "Medium", "High", "Critical"}


def _load_lab(db: Session, lab_id: str) -> Lab | None:
    return (
        db.query(Lab)
        .options(
            joinedload(Lab.template),
            joinedload(Lab.services),
            joinedload(Lab.target_applications),
            joinedload(Lab.defense_actions),
            joinedload(Lab.simulations),
        )
        .filter(Lab.id == lab_id)
        .first()
    )


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9-]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-+", "-", slug)
    return slug[:58].strip("-") or f"app-{uuid4().hex[:8]}"


def _assert_safe_service_name(service_name: str) -> None:
    if not _SERVICE_RE.match(service_name) or len(service_name) > 63:
        raise HTTPException(
            status_code=400,
            detail="Service name must be a Kubernetes DNS label using lowercase letters, numbers, and hyphens.",
        )


def _target_service_names(lab: Lab) -> set[str]:
    return {item.service_name for item in lab.services}


@router.post("/labs/{lab_id}/target-apps", status_code=status.HTTP_201_CREATED)
def create_target_application(
    lab_id: str,
    payload: TargetApplicationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    if lab.status not in {"Running", "Stopped"}:
        raise HTTPException(status_code=409, detail="Lab must exist before importing a target app")

    app_name = (payload.app_name or payload.appName or "").strip()
    if not app_name:
        raise HTTPException(status_code=400, detail="appName is required")

    import_type = (payload.import_type or payload.importType or "docker-image").strip().lower()
    if import_type not in _ALLOWED_IMPORT_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported import type")

    service_name = (payload.service_name or payload.serviceName or _slug(app_name)).strip().lower()
    _assert_safe_service_name(service_name)
    if service_name in _target_service_names(lab):
        raise HTTPException(status_code=409, detail="A service with this name already exists in the lab")

    health_path = (payload.health_path or payload.healthPath or "/").strip() or "/"
    if not health_path.startswith("/"):
        health_path = f"/{health_path}"

    image = (payload.image or "").strip() or None
    manifest = payload.manifest or None
    local_url = payload.local_url or payload.localUrl or None
    normal_paths = payload.normal_paths or payload.normalPaths or [f"GET {health_path}"]

    if import_type == "docker-image" and not image:
        raise HTTPException(status_code=400, detail="Docker image import requires an image name")
    if import_type == "kubernetes-yaml" and not manifest:
        raise HTTPException(status_code=400, detail="Kubernetes YAML import requires a manifest")
    if import_type == "local-service" and settings.kubernetes_mode == "real" and not image:
        raise HTTPException(
            status_code=400,
            detail="Real Kubernetes mode cannot target external local URLs. Build the app as an image or provide constrained YAML.",
        )

    internal_url = f"http://{service_name}:{payload.port}"
    target = TargetApplication(
        lab_id=lab.id,
        app_name=app_name,
        service_name=service_name,
        import_type=import_type,
        image=image,
        port=payload.port,
        health_path=health_path,
        status="Provisioning",
        internal_url=internal_url,
        safety_state="Contained",
        manifest_json={
            "manifest": manifest,
            "local_url": local_url,
            "normal_paths": normal_paths,
            "safety_boundary": "lab-namespace-only",
        },
    )
    db.add(target)
    service_instance = ServiceInstance(
        lab_id=lab.id,
        service_name=service_name,
        service_type="target-app",
        kubernetes_deployment_name=service_name,
        kubernetes_service_name=service_name,
        status="Provisioning",
        port=payload.port,
        exposed=False,
    )
    db.add(service_instance)
    db.flush()

    try:
        KubernetesService().deploy_target_application(lab.namespace, _target_to_service_definition(target))
        target.status = "Running" if lab.status == "Running" else "Registered"
        service_instance.status = target.status
    except KubernetesProvisioningError as exc:
        target.status = "Failed"
        service_instance.status = "Failed"
        lab.error_message = str(exc)

    db.commit()
    db.expire_all()
    loaded = _load_lab(db, lab.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Target app was created but lab could not be loaded")
    created = next((item for item in loaded.target_applications if item.service_name == service_name), None)
    if not created:
        raise HTTPException(status_code=500, detail="Target app was created but could not be loaded")
    return {"targetApplication": target_application_to_api(created), "lab": lab_to_api(loaded)}


@router.get("/labs/{lab_id}/target-apps", response_model=dict[str, list[TargetApplicationOut]])
def list_target_applications(
    lab_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    return {"targetApplications": [target_application_to_api(item) for item in lab.target_applications]}


@router.post("/labs/{lab_id}/custom-scenarios", response_model=dict[str, ScenarioOut], status_code=status.HTTP_201_CREATED)
def create_custom_scenario(
    lab_id: str,
    payload: CustomScenarioCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")

    target_service = (payload.target_service or payload.targetService or "").strip()
    if not target_service:
        raise HTTPException(status_code=400, detail="targetService is required")
    if "://" in target_service or "/" in target_service or target_service not in _target_service_names(lab):
        raise HTTPException(status_code=400, detail="Custom scenario target must be an internal service in this lab")

    method = payload.method.upper().strip()
    if method not in _ALLOWED_METHODS:
        raise HTTPException(status_code=400, detail="Unsupported HTTP method for safe scenario template")

    endpoint = payload.endpoint.strip() or "/"
    if "://" in endpoint:
        raise HTTPException(status_code=400, detail="Endpoint must be a path, not a URL")
    if not endpoint.startswith("/"):
        endpoint = f"/{endpoint}"

    attack_type = (payload.attack_type or payload.attackType or "Custom Web App Probe").strip()
    payload_category = (payload.payload_category or payload.payloadCategory or "custom_probe").strip()
    risk_level = (payload.risk_level or payload.riskLevel or "Medium").strip()
    if risk_level not in _ALLOWED_RISKS:
        risk_level = "Medium"
    request_count = payload.request_count or payload.requestCount or 12

    scenario = AttackScenario(
        id=f"custom-{lab.id[:8]}-{uuid4().hex[:8]}",
        scenario_name=payload.name,
        description=f"User-defined safe scenario targeting {target_service} inside {lab.namespace}.",
        difficulty="Custom",
        attack_type=attack_type,
        scenario_config_json={
            "is_custom": True,
            "custom_lab_id": lab.id,
            "allowed_template_ids": [lab.template_id],
            "target_services": [target_service],
            "default_risk": risk_level,
            "steps": [
                {
                    "order": 1,
                    "action_type": "CUSTOM_WEB_APP_REQUEST_PATTERN",
                    "source": "attack-pod",
                    "target": target_service,
                    "method": method,
                    "endpoint": endpoint,
                    "event_type": "custom_web_app_signal",
                    "payload_category": payload_category,
                    "status_code": 200,
                    "count": request_count,
                }
            ],
        },
    )
    db.add(scenario)
    db.commit()
    db.refresh(scenario)
    return {"scenario": scenario_to_api(scenario)}


def _target_to_service_definition(target: TargetApplication) -> dict:
    return {
        "name": target.service_name,
        "type": "target-app",
        "port": target.port,
        "exposed": False,
        "image": target.image,
        "import_type": target.import_type,
        "health_path": target.health_path,
        "manifest": target.manifest_json.get("manifest"),
        "local_url": target.manifest_json.get("local_url"),
        "normal_paths": target.manifest_json.get("normal_paths", []),
    }
