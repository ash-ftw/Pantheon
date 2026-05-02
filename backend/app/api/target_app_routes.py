from __future__ import annotations

import re
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.database import get_db
from app.dependencies import can_access_lab, get_current_user
from app.models import AttackScenario, Lab, ServiceInstance, TargetApplication, User, utcnow
from app.schemas import CustomScenarioCreate, ScenarioOut, TargetApplicationCreate, TargetApplicationOut
from app.services.kubernetes_service import KubernetesProvisioningError, KubernetesService
from app.services.presenters import lab_to_api, scenario_to_api, target_application_to_api
from app.services.simulation_service import service_definitions_for_lab

router = APIRouter(tags=["target-applications"])

_SERVICE_RE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_ALLOWED_IMPORT_TYPES = {"docker-image", "kubernetes-yaml", "local-service"}
_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"}
_ALLOWED_RISKS = {"Low", "Medium", "High", "Critical"}
_HEALTHY_TARGET_STATUSES = {"Healthy"}


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


def _target_application_by_service(lab: Lab, service_name: str) -> TargetApplication | None:
    return next((item for item in lab.target_applications if item.service_name == service_name), None)


def _service_instance_by_name(lab: Lab, service_name: str) -> ServiceInstance | None:
    return next((item for item in lab.services if item.service_name == service_name), None)


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


@router.post("/labs/{lab_id}/target-apps/{target_id}/validate")
def validate_target_application_health(
    lab_id: str,
    target_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    lab = _load_lab(db, lab_id)
    if not lab or not can_access_lab(user, lab.user_id):
        raise HTTPException(status_code=404, detail="Lab not found")
    target = next((item for item in lab.target_applications if item.id == target_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Target application not found")

    service_instance = _service_instance_by_name(lab, target.service_name)
    health = {
        "serviceName": target.service_name,
        "healthPath": target.health_path,
        "ready": False,
        "status": "Unknown",
        "message": "",
        "observedAt": utcnow().isoformat(),
    }
    try:
        status_payload = KubernetesService().get_lab_status(lab.namespace, service_definitions_for_lab(lab))
        service_status = next(
            (item for item in status_payload.get("services", []) if item.get("name") == target.service_name),
            None,
        )
        service_state = service_status.get("status", "Missing") if service_status else "Missing"
        ready = service_state == "Running"
        health.update(
            {
                "ready": ready,
                "status": service_state,
                "message": "Target app is ready for internal scenarios."
                if ready
                else "Target app is not ready. Check pod status and service configuration before running scenarios.",
                "details": service_status or {},
            }
        )
        target.status = "Healthy" if ready else "Unhealthy"
        if service_instance:
            service_instance.status = "Running" if ready else service_state
        lab.error_message = None if ready else health["message"]
    except KubernetesProvisioningError as exc:
        health.update({"ready": False, "status": "Unhealthy", "message": str(exc)})
        target.status = "Unhealthy"
        if service_instance:
            service_instance.status = "Unhealthy"
        lab.error_message = str(exc)

    target.manifest_json = {
        **(target.manifest_json or {}),
        "health_validation": health,
    }
    db.commit()
    loaded = _load_lab(db, lab.id)
    if not loaded:
        raise HTTPException(status_code=500, detail="Target app was validated but lab could not be loaded")
    validated = next((item for item in loaded.target_applications if item.id == target_id), None)
    return {
        "targetApplication": target_application_to_api(validated or target),
        "health": health,
        "lab": lab_to_api(loaded),
    }


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
    raw_steps = payload.steps or []
    if not target_service and not raw_steps:
        raise HTTPException(status_code=400, detail="targetService is required")

    attack_type = (payload.attack_type or payload.attackType or "Custom Web App Probe").strip()
    risk_level = (payload.risk_level or payload.riskLevel or "Medium").strip()
    if risk_level not in _ALLOWED_RISKS:
        risk_level = "Medium"
    steps = _scenario_steps_from_payload(payload, lab, target_service)
    target_services = []
    for step in steps:
        if step["target"] not in target_services:
            target_services.append(step["target"])

    scenario = AttackScenario(
        id=f"custom-{lab.id[:8]}-{uuid4().hex[:8]}",
        scenario_name=payload.name,
        description=f"User-defined safe scenario targeting {', '.join(target_services)} inside {lab.namespace}.",
        difficulty="Custom",
        attack_type=attack_type,
        scenario_config_json={
            "is_custom": True,
            "custom_lab_id": lab.id,
            "allowed_template_ids": [lab.template_id],
            "target_services": target_services,
            "default_risk": risk_level,
            "steps": steps,
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


def _scenario_steps_from_payload(payload: CustomScenarioCreate, lab: Lab, fallback_target: str) -> list[dict]:
    raw_steps = payload.steps or []
    if not raw_steps:
        raw_steps = [
            {
                "target": fallback_target,
                "method": payload.method,
                "endpoint": payload.endpoint,
                "payload_category": payload.payload_category or payload.payloadCategory,
                "expected_signal": payload.expected_signal or payload.expectedSignal,
                "count": payload.request_count or payload.requestCount,
                "rate_limit_per_minute": payload.rate_limit_per_minute or payload.rateLimitPerMinute,
            }
        ]

    steps: list[dict] = []
    for index, raw_step in enumerate(raw_steps, start=1):
        target = str(raw_step.get("target") or raw_step.get("target_service") or raw_step.get("targetService") or "").strip()
        _assert_internal_target_ready(lab, target)

        method = str(raw_step.get("method") or "GET").upper().strip()
        if method not in _ALLOWED_METHODS:
            raise HTTPException(status_code=400, detail=f"Unsupported HTTP method in step {index}")

        endpoint = str(raw_step.get("endpoint") or "/").strip() or "/"
        if "://" in endpoint:
            raise HTTPException(status_code=400, detail=f"Step {index} endpoint must be a path, not a URL")
        if not endpoint.startswith("/") and not endpoint.startswith("tcp/"):
            endpoint = f"/{endpoint}"

        payload_category = str(raw_step.get("payload_category") or raw_step.get("payloadCategory") or "custom_probe").strip()
        event_type = str(
            raw_step.get("expected_signal")
            or raw_step.get("expectedSignal")
            or raw_step.get("event_type")
            or raw_step.get("eventType")
            or "custom_web_app_signal"
        ).strip()
        count = int(raw_step.get("count") or raw_step.get("request_count") or raw_step.get("requestCount") or 12)
        count = max(1, min(count, 100))
        rate_limit = raw_step.get("rate_limit_per_minute") or raw_step.get("rateLimitPerMinute")
        rate_limit_value = max(1, min(int(rate_limit), 600)) if rate_limit else None

        step = {
            "order": index,
            "action_type": str(raw_step.get("action_type") or raw_step.get("actionType") or "CUSTOM_WEB_APP_REQUEST_PATTERN"),
            "source": str(raw_step.get("source") or "attack-pod"),
            "target": target,
            "method": method,
            "endpoint": endpoint,
            "event_type": event_type,
            "payload_category": payload_category,
            "status_code": int(raw_step.get("status_code") or raw_step.get("statusCode") or 200),
            "count": count,
        }
        if rate_limit_value:
            step["rate_limit_per_minute"] = rate_limit_value
        steps.append(step)
    return steps


def _assert_internal_target_ready(lab: Lab, target_service: str) -> None:
    if not target_service or "://" in target_service or "/" in target_service or target_service not in _target_service_names(lab):
        raise HTTPException(status_code=400, detail="Custom scenario target must be an internal service in this lab")
    target_app = _target_application_by_service(lab, target_service)
    if target_app and target_app.status not in _HEALTHY_TARGET_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Validate health for target app {target_service} before creating scenarios.",
        )
