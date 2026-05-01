from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.catalog import DEFENSES
from app.config import settings
from app.models import (
    AIAnalysis,
    AttackScenario,
    DefenseAction,
    DefenseRecommendation,
    Lab,
    Report,
    SimulationLog,
    SimulationRun,
    utcnow,
    uuid_str,
)
from app.services.kubernetes_service import KubernetesService


def active_defense_actions(db: Session, lab_id: str) -> list[DefenseAction]:
    return (
        db.query(DefenseAction)
        .filter(DefenseAction.lab_id == lab_id, DefenseAction.status == "Applied")
        .order_by(DefenseAction.applied_at)
        .all()
    )


def defense_catalog_by_id(catalog_id: str) -> dict[str, Any] | None:
    return next((item for item in DEFENSES if item["id"] == catalog_id), None)


def service_definitions_for_lab(lab: Lab) -> list[dict[str, Any]]:
    target_by_service = {target.service_name: target for target in lab.target_applications}
    definitions: list[dict[str, Any]] = []

    if lab.services:
        for item in lab.services:
            definition: dict[str, Any] = {
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

    if definitions:
        return definitions
    return lab.template.service_config_json.get("services", [])


def normal_traffic_for_lab(lab: Lab) -> list[str]:
    traffic = list(lab.template.normal_traffic_json)
    for target in lab.target_applications:
        for entry in target.manifest_json.get("normal_paths", []):
            if isinstance(entry, str) and entry not in traffic:
                traffic.append(entry)
    return traffic


def run_simulation(db: Session, lab: Lab, scenario: AttackScenario) -> SimulationRun:
    template = lab.template
    config = scenario.scenario_config_json
    service_definitions = service_definitions_for_lab(lab)
    normal_traffic = normal_traffic_for_lab(lab)
    normalized_config = _normalized_scenario_config(config, service_definitions)
    active_actions = active_defense_actions(db, lab.id)
    active_action_types = {action.action_type for action in active_actions}
    started_at = utcnow()
    simulation_id = uuid_str()
    generated_logs = _normal_logs(lab.id, simulation_id, normal_traffic, service_definitions, started_at)
    reached_services: list[str] = []
    path_steps: list[dict[str, Any]] = []
    suspicious_event_count = 0
    blocked = False
    blocked_at = None

    for raw_step in normalized_config.get("steps", []):
        step = {
            **raw_step,
            "source": raw_step.get("source", ""),
            "target": raw_step.get("target", ""),
        }
        should_block = _defense_blocks_step(scenario.attack_type, step, active_action_types)
        event_count = max(1, int(step["count"] * 0.35)) if should_block else int(step["count"])
        normalized_step = {**step, "count": event_count, "blocked": should_block}
        path_steps.append(normalized_step)
        reached_services.append(step["target"])
        suspicious_event_count += event_count

        for _ in range(event_count):
            generated_logs.append(
                {
                    "timestamp": started_at + timedelta(milliseconds=len(generated_logs) * 550),
                    "source_service": step["source"],
                    "target_service": step["target"],
                    "method": step["method"],
                    "endpoint": step["endpoint"],
                    "status_code": 403 if should_block else int(step["status_code"]),
                    "request_count": 1,
                    "payload_category": step["payload_category"],
                    "event_type": "blocked_by_defense" if should_block else step["event_type"],
                    "severity": "Warning" if should_block else "Critical" if _risk_rank(config.get("default_risk")) >= 4 else "High",
                    "is_attack_simulation": True,
                    "raw_log_json": {
                        "action_type": step["action_type"],
                        "expected_signal": step["event_type"],
                        "safe_simulation": True,
                    },
                }
            )

        if should_block:
            blocked = True
            blocked_at = step["target"]
            break

    if settings.kubernetes_mode == "real":
        generated_logs = [
            _coerce_job_log_record(item, started_at)
            for item in KubernetesService().run_simulation_jobs(
                namespace=lab.namespace,
                simulation_id=simulation_id,
                services=service_definitions,
                scenario_config=normalized_config,
                normal_traffic=normal_traffic,
            )
        ]
        attack_logs = [
            item
            for item in generated_logs
            if item["is_attack_simulation"] and item["event_type"] != "simulation_job_completed"
        ]
        suspicious_event_count = len(attack_logs)
        blocked_log = next((item for item in attack_logs if item["event_type"] == "blocked_by_defense"), None)
        blocked = blocked_log is not None
        blocked_at = blocked_log["target_service"] if blocked_log else None
        reached_services = []
        for item in attack_logs:
            target = item["target_service"]
            if target not in {"attack-runner", "traffic-generator"}:
                reached_services.append(target)
        if blocked and blocked_at:
            path_steps = [step for step in path_steps if step["target"] in reached_services]
            if not path_steps or path_steps[-1]["target"] != blocked_at:
                path_steps.append(
                    {
                        "source": blocked_log["source_service"],
                        "target": blocked_at,
                        "count": 1,
                        "blocked": True,
                    }
                )

    attack_path = _create_attack_path(service_definitions, path_steps, blocked_at)
    risk_level = _risk_after_defense(config.get("default_risk", "Medium"), blocked)
    analysis = _analyze_simulation(scenario.attack_type, risk_level, reached_services, blocked, suspicious_event_count)
    comparison = (
        _build_comparison(db, lab.id, scenario.id, reached_services, risk_level, suspicious_event_count, blocked)
        if active_actions
        else None
    )
    result_summary = (
        f"Attack was blocked at {blocked_at} after {suspicious_event_count} suspicious event(s)."
        if blocked
        else f"Attack completed its simulated path through {' -> '.join(reached_services)}."
    )

    simulation = SimulationRun(
        id=simulation_id,
        lab_id=lab.id,
        scenario_id=scenario.id,
        scenario_name=scenario.scenario_name,
        attack_type=scenario.attack_type,
        status="Completed",
        started_at=started_at,
        completed_at=utcnow(),
        risk_level=risk_level,
        result_summary=result_summary,
        blocked=blocked,
        blocked_at=blocked_at,
        reached_services_json=reached_services,
        suspicious_event_count=suspicious_event_count,
        applied_defenses_json=[action.action_type for action in active_actions],
        attack_path_json=attack_path,
        comparison_json=comparison,
    )
    if simulation.comparison_json:
        simulation.comparison_json["postDefenseSimulationId"] = simulation.id
    db.add(simulation)
    db.flush()

    for log in generated_logs:
        db.add(
            SimulationLog(
                simulation_id=simulation.id,
                lab_id=lab.id,
                **log,
            )
        )

    db.add(
        AIAnalysis(
            simulation_id=simulation.id,
            classification=analysis["classification"],
            confidence_score=analysis["confidence_score"],
            risk_level=analysis["risk_level"],
            explanation=analysis["explanation"],
            recommended_defense_categories_json=analysis["recommended_defense_categories"],
        )
    )

    for recommendation in _recommendations_for_simulation(simulation.id, scenario.attack_type, active_action_types):
        db.add(DefenseRecommendation(**recommendation))

    db.commit()
    return simulation


def create_report(db: Session, simulation: SimulationRun) -> Report:
    if simulation.report:
        return simulation.report

    lab = simulation.lab
    scenario = simulation.scenario
    report = Report(
        simulation_id=simulation.id,
        lab_id=lab.id,
        title=f"{scenario.scenario_name} Report",
        summary=simulation.result_summary,
        report_json={
            "labInformation": {
                "labId": lab.id,
                "labName": lab.lab_name,
                "namespace": lab.namespace,
                "status": lab.status,
            },
            "organizationTemplate": lab.template.name,
            "targetApplications": [
                {
                    "appName": target.app_name,
                    "serviceName": target.service_name,
                    "internalUrl": target.internal_url,
                    "status": target.status,
                    "safetyState": target.safety_state,
                }
                for target in lab.target_applications
            ],
            "attackScenario": {
                "id": scenario.id,
                "name": scenario.scenario_name,
                "attackType": scenario.attack_type,
                "difficulty": scenario.difficulty,
            },
            "timelineOfEvents": [_log_record(item) for item in simulation.logs[:25]],
            "attackPath": simulation.attack_path_json,
            "aiClassification": _analysis_record(simulation.ai_analysis),
            "riskLevel": simulation.risk_level,
            "defenseRecommendations": [_recommendation_record(item) for item in simulation.recommendations],
            "appliedDefenses": [_defense_action_record(item) for item in active_defense_actions(db, lab.id)],
            "beforeAfterComparison": simulation.comparison_json,
            "conclusion": (
                "The selected defensive controls reduced the simulated attack path."
                if simulation.blocked
                else "The simulation completed without an active control blocking the attack path."
            ),
        },
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def apply_defenses(
    db: Session,
    lab: Lab,
    defense_ids: list[str],
    simulation_id: str | None = None,
    recommendation_id: str | None = None,
) -> list[DefenseAction]:
    applied: list[DefenseAction] = []
    for defense_id in defense_ids:
        catalog = defense_catalog_by_id(defense_id)
        if not catalog:
            continue
        existing = (
            db.query(DefenseAction)
            .filter(
                DefenseAction.lab_id == lab.id,
                DefenseAction.action_type == catalog["action_type"],
                DefenseAction.status == "Applied",
            )
            .first()
        )
        if existing:
            applied.append(existing)
            continue
        action = DefenseAction(
            lab_id=lab.id,
            simulation_id=simulation_id,
            recommendation_id=recommendation_id,
            catalog_id=catalog["id"],
            action_type=catalog["action_type"],
            title=catalog["name"],
            status="Applied",
            details_json={
                "mode": "safe_simulation",
                "kubernetes_changes": "network-policy-ready" if catalog["action_type"] == "NETWORK_POLICY" else "not-required",
            },
        )
        db.add(action)
        applied.append(action)
        KubernetesService().apply_defense(
            lab.namespace,
            catalog["action_type"],
            service_definitions_for_lab(lab),
        )
    db.commit()
    for action in applied:
        db.refresh(action)
    return applied


def _normalized_scenario_config(config: dict[str, Any], service_definitions: list[dict[str, Any]]) -> dict[str, Any]:
    normalized = {**config, "steps": []}
    for raw_step in config.get("steps", []):
        normalized["steps"].append(
            {
                **raw_step,
                "source": _normalize_source_for_template(raw_step.get("source", ""), service_definitions),
                "target": _normalize_target_for_template(raw_step.get("target", ""), service_definitions),
            }
        )
    return normalized


def _coerce_job_log_record(record: dict[str, Any], fallback_time: datetime) -> dict[str, Any]:
    timestamp = record.get("timestamp")
    if isinstance(timestamp, str):
        try:
            parsed_timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            parsed_timestamp = fallback_time
    elif isinstance(timestamp, datetime):
        parsed_timestamp = timestamp
    else:
        parsed_timestamp = fallback_time
    if parsed_timestamp.tzinfo is None:
        parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
    raw_log = record.get("raw_log_json", {})
    return {
        "timestamp": parsed_timestamp,
        "source_service": str(record.get("source_service", "runner")),
        "target_service": str(record.get("target_service", "unknown")),
        "method": str(record.get("method", "GET")),
        "endpoint": str(record.get("endpoint", "/")),
        "status_code": int(record.get("status_code", 0) or 0),
        "request_count": int(record.get("request_count", 1) or 1),
        "payload_category": str(record.get("payload_category", "runner_event")),
        "event_type": str(record.get("event_type", "runner_event")),
        "severity": str(record.get("severity", "Info")),
        "is_attack_simulation": bool(record.get("is_attack_simulation", False)),
        "raw_log_json": raw_log if isinstance(raw_log, dict) else {},
    }


def _normal_logs(
    lab_id: str,
    simulation_id: str,
    normal_traffic: list[str],
    service_definitions: list[dict[str, Any]],
    started_at,
) -> list[dict[str, Any]]:
    services = service_definitions or [{"name": "frontend-service"}]
    logs: list[dict[str, Any]] = []
    for index, entry in enumerate(normal_traffic[:8]):
        parts = entry.split(" ", 1)
        method = parts[0]
        endpoint = parts[1] if len(parts) > 1 else "/"
        logs.append(
            {
                "timestamp": started_at + timedelta(milliseconds=index * 400),
                "source_service": "traffic-generator",
                "target_service": services[index % len(services)]["name"],
                "method": method,
                "endpoint": endpoint,
                "status_code": 200,
                "request_count": 1,
                "payload_category": "normal_user_behavior",
                "event_type": "normal_request",
                "severity": "Info",
                "is_attack_simulation": False,
                "raw_log_json": {"generated_by": "pantheon-normal-traffic", "lab_id": lab_id, "simulation_id": simulation_id},
            }
        )
    return logs


def _normalize_target_for_template(target: str, service_definitions: list[dict[str, Any]]) -> str:
    service_names = {service["name"] for service in service_definitions}
    if target in service_names:
        return target
    fallback_map = {
        "employee-api": ["employee-api", "marks-api", "product-service"],
        "frontend-service": ["frontend-service", "student-portal"],
        "admin-api": ["admin-api", "payment-service"],
    }
    for candidate in fallback_map.get(target, [target]):
        if candidate in service_names:
            return candidate
    return target


def _normalize_source_for_template(source: str, service_definitions: list[dict[str, Any]]) -> str:
    service_names = {service["name"] for service in service_definitions}
    if source in service_names or source == "attack-pod":
        return source
    if source == "frontend-service" and "student-portal" in service_names:
        return "student-portal"
    if source == "employee-api" and "marks-api" in service_names:
        return "marks-api"
    if source == "employee-api" and "product-service" in service_names:
        return "product-service"
    return source


def _defense_blocks_step(attack_type: str, step: dict[str, Any], active_action_types: set[str]) -> bool:
    event_type = step["event_type"]
    target = step["target"]
    if "RATE_LIMIT" in active_action_types and attack_type in {"Brute Force", "DDoS-Style Traffic"}:
        return event_type in {"failed_login", "resource_exhaustion_pattern"}
    if "INPUT_VALIDATION" in active_action_types and attack_type in {"SQL Injection", "Multi-Stage Attack"}:
        return event_type == "suspicious_input_pattern"
    if "ENDPOINT_RESTRICTION" in active_action_types and attack_type in {
        "Privilege Escalation",
        "Lateral Movement",
        "Multi-Stage Attack",
    }:
        return event_type == "restricted_endpoint_access"
    if "NETWORK_POLICY" in active_action_types and attack_type in {"Lateral Movement", "Multi-Stage Attack"}:
        return target in {"admin-api", "postgres-db", "payment-service"} or event_type == "database_reachability_attempt"
    if "RESOURCE_LIMIT" in active_action_types and attack_type == "DDoS-Style Traffic":
        return event_type == "resource_exhaustion_pattern"
    return False


def _risk_after_defense(default_risk: str, blocked: bool) -> str:
    if not blocked:
        return default_risk
    if default_risk == "Critical":
        return "Medium"
    if default_risk == "High":
        return "Low"
    return "Low"


def _risk_rank(risk: str | None) -> int:
    return {"Low": 1, "Medium": 2, "High": 3, "Critical": 4}.get(risk or "", 0)


def _create_attack_path(
    service_definitions: list[dict[str, Any]],
    steps: list[dict[str, Any]],
    blocked_target: str | None,
) -> dict[str, Any]:
    node_ids = {"attack-pod"}
    for step in steps:
        node_ids.add(step["source"])
        node_ids.add(step["target"])
    service_names = {service["name"] for service in service_definitions}
    nodes = []
    for node_id in node_ids:
        state = "normal"
        if node_id == "attack-pod":
            state = "targeted"
        if any(step["target"] == node_id for step in steps):
            state = "suspicious"
        if not blocked_target and steps and node_id == steps[-1]["target"]:
            state = "compromised"
        if blocked_target and node_id == blocked_target:
            state = "blocked"
        if blocked_target and node_id in service_names and not any(step["target"] == node_id for step in steps):
            state = "protected"
        nodes.append({"id": node_id, "label": node_id.replace("-", " "), "state": state})
    edges = [
        {
            "from": step["source"],
            "to": step["target"],
            "eventCount": step["count"],
            "blocked": blocked_target == step["target"] and step["blocked"],
        }
        for step in steps
    ]
    return {"nodes": nodes, "edges": edges}


def _analyze_simulation(
    attack_type: str,
    risk_level: str,
    reached_targets: list[str],
    blocked: bool,
    suspicious_events: int,
) -> dict[str, Any]:
    confidence = min(0.98, max(0.72, 0.82 + len(reached_targets) * 0.025 + suspicious_events / 500))
    movement_text = (
        f" across {', '.join(reached_targets)}" if len(reached_targets) > 1 else f" against {reached_targets[0] if reached_targets else 'the lab'}"
    )
    block_text = " A configured defense blocked the sequence before it reached its original depth." if blocked else ""
    return {
        "classification": attack_type,
        "confidence_score": round(confidence, 2),
        "risk_level": risk_level,
        "explanation": (
            f"The request sequence matches {attack_type.lower()} behavior{movement_text}, "
            f"with {suspicious_events} suspicious event(s).{block_text}"
        ),
        "recommended_defense_categories": [
            defense["recommendation_type"] for defense in DEFENSES if attack_type in defense["attack_types"]
        ],
    }


def _recommendations_for_simulation(
    simulation_id: str,
    attack_type: str,
    active_action_types: set[str],
) -> list[dict[str, Any]]:
    recommendations = []
    for defense in DEFENSES:
        if attack_type not in defense["attack_types"]:
            continue
        recommendations.append(
            {
                "simulation_id": simulation_id,
                "catalog_id": defense["id"],
                "recommendation_type": defense["recommendation_type"],
                "action_type": defense["action_type"],
                "title": defense["name"],
                "description": defense["description"],
                "defense_level": defense["defense_level"],
                "priority": defense["priority"],
                "is_applicable": defense["action_type"] not in active_action_types,
                "already_applied": defense["action_type"] in active_action_types,
            }
        )
    return recommendations


def _build_comparison(
    db: Session,
    lab_id: str,
    scenario_id: str,
    reached_services: list[str],
    risk_level: str,
    suspicious_event_count: int,
    blocked: bool,
) -> dict[str, Any] | None:
    baselines = (
        db.query(SimulationRun)
        .filter(SimulationRun.lab_id == lab_id, SimulationRun.scenario_id == scenario_id)
        .order_by(SimulationRun.completed_at.desc())
        .all()
    )
    baseline = next((item for item in baselines if not item.applied_defenses_json), None)
    if not baseline:
        return None
    baseline_depth = len(baseline.reached_services_json)
    current_depth = len(reached_services)
    depth_reduction = max(0, round(((baseline_depth - current_depth) / baseline_depth) * 100)) if baseline_depth else 0
    return {
        "baselineSimulationId": baseline.id,
        "postDefenseSimulationId": None,
        "before": {
            "reachedServices": baseline.reached_services_json,
            "riskLevel": baseline.risk_level,
            "suspiciousEvents": baseline.suspicious_event_count,
        },
        "after": {
            "reachedServices": reached_services,
            "riskLevel": risk_level,
            "suspiciousEvents": suspicious_event_count,
        },
        "improvement": {
            "attackDepthReducedPercent": depth_reduction,
            "suspiciousEventsReducedBy": max(0, baseline.suspicious_event_count - suspicious_event_count),
            "blockedEarlier": blocked and current_depth <= baseline_depth,
        },
    }


def _log_record(log: SimulationLog) -> dict[str, Any]:
    return {
        "timestamp": log.timestamp.isoformat(),
        "sourceService": log.source_service,
        "targetService": log.target_service,
        "method": log.method,
        "endpoint": log.endpoint,
        "statusCode": log.status_code,
        "eventType": log.event_type,
        "severity": log.severity,
        "isAttackSimulation": log.is_attack_simulation,
    }


def _analysis_record(analysis: AIAnalysis | None) -> dict[str, Any] | None:
    if not analysis:
        return None
    return {
        "classification": analysis.classification,
        "confidenceScore": analysis.confidence_score,
        "riskLevel": analysis.risk_level,
        "explanation": analysis.explanation,
    }


def _recommendation_record(recommendation: DefenseRecommendation) -> dict[str, Any]:
    return {
        "catalogId": recommendation.catalog_id,
        "title": recommendation.title,
        "recommendationType": recommendation.recommendation_type,
        "defenseLevel": recommendation.defense_level,
        "priority": recommendation.priority,
        "description": recommendation.description,
    }


def _defense_action_record(action: DefenseAction) -> dict[str, Any]:
    return {
        "catalogId": action.catalog_id,
        "title": action.title,
        "actionType": action.action_type,
        "status": action.status,
        "appliedAt": action.applied_at.isoformat(),
    }
