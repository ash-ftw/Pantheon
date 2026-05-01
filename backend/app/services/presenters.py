from __future__ import annotations

from app.models import (
    AIAnalysis,
    AttackScenario,
    DefenseAction,
    DefenseRecommendation,
    Lab,
    OrganizationTemplate,
    Report,
    SimulationLog,
    SimulationRun,
)


def template_to_api(template: OrganizationTemplate) -> dict:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "services": template.service_config_json.get("services", []),
        "normalTraffic": template.normal_traffic_json,
    }


def scenario_to_api(scenario: AttackScenario) -> dict:
    config = scenario.scenario_config_json
    return {
        "id": scenario.id,
        "name": scenario.scenario_name,
        "description": scenario.description,
        "difficulty": scenario.difficulty,
        "attackType": scenario.attack_type,
        "allowedTemplateIds": config.get("allowed_template_ids", []),
        "targetServices": config.get("target_services", []),
        "defaultRisk": config.get("default_risk", "Medium"),
    }


def lab_to_api(lab: Lab) -> dict:
    latest_simulation = lab.simulations[-1] if lab.simulations else None
    return {
        "id": lab.id,
        "userId": lab.user_id,
        "templateId": lab.template_id,
        "labName": lab.lab_name,
        "namespace": lab.namespace,
        "status": lab.status,
        "deploymentMode": lab.deployment_mode,
        "errorMessage": lab.error_message,
        "createdAt": lab.created_at,
        "deletedAt": lab.deleted_at,
        "template": template_to_api(lab.template),
        "services": [service_to_api(item) for item in lab.services],
        "activeDefenses": [defense_action_to_api(item) for item in lab.defense_actions if item.status == "Applied"],
        "latestSimulation": simulation_to_api(latest_simulation) if latest_simulation else None,
    }


def service_to_api(service) -> dict:
    return {
        "id": service.id,
        "labId": service.lab_id,
        "serviceName": service.service_name,
        "serviceType": service.service_type,
        "kubernetesDeploymentName": service.kubernetes_deployment_name,
        "kubernetesServiceName": service.kubernetes_service_name,
        "status": service.status,
        "port": service.port,
        "exposed": service.exposed,
        "createdAt": service.created_at,
    }


def log_to_api(log: SimulationLog) -> dict:
    return {
        "id": log.id,
        "timestamp": log.timestamp,
        "labId": log.lab_id,
        "simulationId": log.simulation_id,
        "sourceService": log.source_service,
        "targetService": log.target_service,
        "method": log.method,
        "endpoint": log.endpoint,
        "statusCode": log.status_code,
        "requestCount": log.request_count,
        "payloadCategory": log.payload_category,
        "eventType": log.event_type,
        "severity": log.severity,
        "isAttackSimulation": log.is_attack_simulation,
        "rawLogJson": log.raw_log_json,
    }


def analysis_to_api(analysis: AIAnalysis | None) -> dict | None:
    if not analysis:
        return None
    return {
        "id": analysis.id,
        "simulationId": analysis.simulation_id,
        "classification": analysis.classification,
        "confidenceScore": analysis.confidence_score,
        "riskLevel": analysis.risk_level,
        "explanation": analysis.explanation,
        "recommendedDefenseCategories": analysis.recommended_defense_categories_json,
        "createdAt": analysis.created_at,
    }


def recommendation_to_api(recommendation: DefenseRecommendation) -> dict:
    return {
        "id": recommendation.id,
        "catalogId": recommendation.catalog_id,
        "simulationId": recommendation.simulation_id,
        "recommendationType": recommendation.recommendation_type,
        "actionType": recommendation.action_type,
        "title": recommendation.title,
        "description": recommendation.description,
        "defenseLevel": recommendation.defense_level,
        "priority": recommendation.priority,
        "isApplicable": recommendation.is_applicable,
        "alreadyApplied": recommendation.already_applied,
        "createdAt": recommendation.created_at,
    }


def defense_action_to_api(action: DefenseAction) -> dict:
    return {
        "id": action.id,
        "labId": action.lab_id,
        "simulationId": action.simulation_id,
        "recommendationId": action.recommendation_id,
        "catalogId": action.catalog_id,
        "actionType": action.action_type,
        "title": action.title,
        "status": action.status,
        "appliedAt": action.applied_at,
        "detailsJson": action.details_json,
    }


def simulation_to_api(simulation: SimulationRun | None) -> dict | None:
    if not simulation:
        return None
    return {
        "id": simulation.id,
        "labId": simulation.lab_id,
        "scenarioId": simulation.scenario_id,
        "scenarioName": simulation.scenario_name,
        "attackType": simulation.attack_type,
        "status": simulation.status,
        "startedAt": simulation.started_at,
        "completedAt": simulation.completed_at,
        "riskLevel": simulation.risk_level,
        "resultSummary": simulation.result_summary,
        "blocked": simulation.blocked,
        "blockedAt": simulation.blocked_at,
        "reachedServices": simulation.reached_services_json,
        "suspiciousEventCount": simulation.suspicious_event_count,
        "appliedDefenseCount": len(simulation.applied_defenses_json),
        "appliedDefenses": simulation.applied_defenses_json,
        "logs": [log_to_api(item) for item in simulation.logs],
        "attackPath": simulation.attack_path_json,
        "aiAnalysis": analysis_to_api(simulation.ai_analysis),
        "recommendations": [recommendation_to_api(item) for item in simulation.recommendations],
        "comparison": simulation.comparison_json,
    }


def report_to_api(report: Report) -> dict:
    return {
        "id": report.id,
        "simulationId": report.simulation_id,
        "labId": report.lab_id,
        "title": report.title,
        "summary": report.summary,
        "createdAt": report.created_at,
        "reportJson": report.report_json,
    }
