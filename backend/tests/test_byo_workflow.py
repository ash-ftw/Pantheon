from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uuid import uuid4

os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{(Path(tempfile.gettempdir()) / f'pantheon_test_{uuid4().hex}.db').as_posix()}"
os.environ["KUBERNETES_MODE"] = "dry-run"
os.environ["PANTHEON_AUTO_CREATE_TABLES"] = "true"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AttackScenario, SimulationJob, SimulationRun, utcnow, uuid_str  # noqa: E402
from app.services.simulation_service import _coerce_job_log_record  # noqa: E402


def auth_headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/auth/login",
        json={"email": "demo@pantheon.local", "password": "pantheon123"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def create_lab(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.post(
        "/api/labs",
        headers=headers,
        json={"lab_name": "BYO API Test", "template_id": "small-company"},
    )
    assert response.status_code == 201, response.text
    return response.json()["lab"]


def test_kubernetes_status_endpoint_returns_dry_run_readiness() -> None:
    with TestClient(app) as client:
        headers = auth_headers(client)
        lab = create_lab(client, headers)

        response = client.get(f"/api/labs/{lab['id']}/kubernetes-status", headers=headers)

        assert response.status_code == 200, response.text
        payload = response.json()["kubernetesStatus"]
        assert payload["labId"] == lab["id"]
        assert payload["namespace"]["phase"] == "DryRun"
        assert payload["summary"]["allReady"] is True
        assert payload["summary"]["readyServices"] == payload["summary"]["totalServices"]
        assert payload["services"]
        assert all(service["status"] == "Running" for service in payload["services"])


def test_observed_kubernetes_log_record_is_normalized() -> None:
    record = {
        "timestamp": "2026-05-01T10:00:00Z",
        "source_service": "kubernetes",
        "target_service": "pantheon-attack-abc123",
        "method": "OBSERVE",
        "endpoint": "k8s/jobs/pantheon-attack-abc123",
        "status_code": 0,
        "request_count": 1,
        "payload_category": "kubernetes_observation",
        "event_type": "kubernetes_job_running",
        "severity": "Info",
        "is_attack_simulation": False,
        "raw_log_json": {"observed_source": "kubernetes_api", "job_name": "pantheon-attack-abc123"},
    }

    normalized = _coerce_job_log_record(record, datetime.now(timezone.utc))

    assert normalized["event_type"] == "kubernetes_job_running"
    assert normalized["method"] == "OBSERVE"
    assert normalized["raw_log_json"]["observed_source"] == "kubernetes_api"
    assert normalized["is_attack_simulation"] is False
    assert normalized["timestamp"].tzinfo is not None


def test_websocket_simulation_stream_returns_progress_and_result() -> None:
    with TestClient(app) as client:
        headers = auth_headers(client)
        token = headers["Authorization"].split(" ", 1)[1]
        lab = create_lab(client, headers)
        events = []

        with client.websocket_connect(
            f"/api/labs/{lab['id']}/simulations/stream?token={token}&scenario_id=brute-force-login"
        ) as websocket:
            while True:
                event = websocket.receive_json()
                events.append(event)
                if event["type"] == "simulation_completed":
                    break

        assert any(event["type"] == "simulation_started" for event in events)
        assert any(event["type"] == "attack_step_completed" for event in events)
        completed = events[-1]
        assert completed["simulation"]["scenarioId"] == "brute-force-login"
        assert completed["simulation"]["logs"]


def test_stop_running_simulation_cancels_active_jobs() -> None:
    with TestClient(app) as client:
        headers = auth_headers(client)
        lab = create_lab(client, headers)
        simulation_id = uuid_str()
        job_id = uuid_str()
        with SessionLocal() as db:
            scenario = db.get(AttackScenario, "brute-force-login")
            simulation = SimulationRun(
                id=simulation_id,
                lab_id=lab["id"],
                scenario_id=scenario.id,
                scenario_name=scenario.scenario_name,
                attack_type=scenario.attack_type,
                status="Running",
                started_at=utcnow(),
                risk_level="Unknown",
                result_summary="Simulation is running.",
                blocked=False,
                reached_services_json=[],
                suspicious_event_count=0,
                applied_defenses_json=[],
                attack_path_json={"nodes": [], "edges": []},
            )
            job = SimulationJob(
                id=job_id,
                simulation_id=simulation_id,
                lab_id=lab["id"],
                namespace=lab["namespace"],
                job_name="pantheon-attack-test",
                job_type="attack",
                status="Running",
                details_json={},
            )
            db.add_all([simulation, job])
            db.commit()

        response = client.post(f"/api/simulations/{simulation_id}/stop", headers=headers)

        assert response.status_code == 200, response.text
        stopped = response.json()["simulation"]
        assert stopped["status"] == "Stopped"
        assert stopped["jobs"][0]["status"] == "Cancelled"

        jobs_response = client.get(f"/api/simulations/{simulation_id}/jobs", headers=headers)
        assert jobs_response.status_code == 200
        assert jobs_response.json()["jobs"][0]["status"] == "Cancelled"


def test_byo_target_custom_scenario_simulation_and_report() -> None:
    with TestClient(app) as client:
        headers = auth_headers(client)
        lab = create_lab(client, headers)
        service_name = f"demo-app-{uuid4().hex[:6]}"

        target_response = client.post(
            f"/api/labs/{lab['id']}/target-apps",
            headers=headers,
            json={
                "appName": "Demo App",
                "serviceName": service_name,
                "importType": "local-service",
                "port": 8080,
                "healthPath": "/health",
            },
        )
        assert target_response.status_code == 201, target_response.text
        target = target_response.json()["targetApplication"]
        assert target["serviceName"] == service_name
        assert target["safetyState"] == "Contained"
        assert target["internalUrl"] == f"http://{service_name}:8080"

        blocked_scenario_response = client.post(
            f"/api/labs/{lab['id']}/custom-scenarios",
            headers=headers,
            json={
                "name": "Blocked Unvalidated Probe",
                "targetService": service_name,
                "endpoint": "/login",
            },
        )
        assert blocked_scenario_response.status_code == 409

        validation_response = client.post(
            f"/api/labs/{lab['id']}/target-apps/{target['id']}/validate",
            headers=headers,
        )
        assert validation_response.status_code == 200, validation_response.text
        assert validation_response.json()["health"]["ready"] is True

        scenario_response = client.post(
            f"/api/labs/{lab['id']}/custom-scenarios",
            headers=headers,
            json={
                "name": "Demo App Login Probe",
                "targetService": service_name,
                "method": "POST",
                "endpoint": "/login",
                "attackType": "SQL Injection",
                "payloadCategory": "sql_meta_characters",
                "riskLevel": "High",
                "requestCount": 5,
                "expectedSignal": "suspicious_input_pattern",
                "rateLimitPerMinute": 45,
            },
        )
        assert scenario_response.status_code == 201, scenario_response.text
        scenario = scenario_response.json()["scenario"]
        assert scenario["isCustom"] is True
        assert scenario["targetLabId"] == lab["id"]
        assert scenario["targetServices"] == [service_name]

        simulation_response = client.post(
            f"/api/labs/{lab['id']}/simulations",
            headers=headers,
            json={"scenario_id": scenario["id"]},
        )
        assert simulation_response.status_code == 201, simulation_response.text
        simulation = simulation_response.json()["simulation"]
        assert service_name in simulation["reachedServices"]
        assert any(log["targetService"] == service_name for log in simulation["logs"])
        assert any(node["id"] == service_name for node in simulation["attackPath"]["nodes"])

        report_response = client.post(
            f"/api/simulations/{simulation['id']}/report",
            headers=headers,
            json={},
        )
        assert report_response.status_code == 201, report_response.text
        report = report_response.json()["report"]
        target_services = [item["serviceName"] for item in report["reportJson"]["targetApplications"]]
        assert service_name in target_services

        pdf_response = client.get(f"/api/reports/{report['id']}/pdf", headers=headers)
        assert pdf_response.status_code == 200, pdf_response.text
        assert pdf_response.headers["content-type"] == "application/pdf"
        assert pdf_response.content.startswith(b"%PDF-1.4")


def test_custom_multi_step_scenario_and_admin_cleanup() -> None:
    with TestClient(app) as client:
        student_headers = auth_headers(client)
        admin_login = client.post(
            "/api/auth/login",
            json={"email": "admin@pantheon.local", "password": "admin123"},
        )
        assert admin_login.status_code == 200, admin_login.text
        admin_headers = {"Authorization": f"Bearer {admin_login.json()['token']}"}
        lab = create_lab(client, student_headers)
        service_name = f"multi-app-{uuid4().hex[:6]}"

        target_response = client.post(
            f"/api/labs/{lab['id']}/target-apps",
            headers=student_headers,
            json={
                "appName": "Multi App",
                "serviceName": service_name,
                "importType": "local-service",
                "port": 8080,
                "healthPath": "/health",
            },
        )
        assert target_response.status_code == 201, target_response.text
        target = target_response.json()["targetApplication"]
        validation_response = client.post(
            f"/api/labs/{lab['id']}/target-apps/{target['id']}/validate",
            headers=student_headers,
        )
        assert validation_response.status_code == 200

        scenario_response = client.post(
            f"/api/labs/{lab['id']}/custom-scenarios",
            headers=student_headers,
            json={
                "name": "Multi Step Probe",
                "attackType": "Custom Web App Probe",
                "riskLevel": "Medium",
                "steps": [
                    {
                        "target": service_name,
                        "method": "GET",
                        "endpoint": "/health",
                        "payloadCategory": "custom_probe",
                        "expectedSignal": "health_probe",
                        "count": 2,
                        "rateLimitPerMinute": 30,
                    },
                    {
                        "target": "auth-service",
                        "method": "POST",
                        "endpoint": "/login",
                        "payloadCategory": "credential_attempt",
                        "expectedSignal": "credential_probe",
                        "count": 3,
                    },
                ],
            },
        )
        assert scenario_response.status_code == 201, scenario_response.text
        scenario = scenario_response.json()["scenario"]
        assert scenario["targetServices"] == [service_name, "auth-service"]

        admin_list = client.get("/api/admin/labs", headers=admin_headers)
        assert admin_list.status_code == 200, admin_list.text
        assert any(item["id"] == lab["id"] and item["owner"]["email"] == "demo@pantheon.local" for item in admin_list.json()["labs"])

        cleanup = client.post(f"/api/admin/labs/{lab['id']}/cleanup", headers=admin_headers)
        assert cleanup.status_code == 200, cleanup.text
        assert cleanup.json()["lab"]["status"] == "Deleted"


def test_custom_scenario_rejects_external_or_unknown_targets() -> None:
    with TestClient(app) as client:
        headers = auth_headers(client)
        lab = create_lab(client, headers)

        external_response = client.post(
            f"/api/labs/{lab['id']}/custom-scenarios",
            headers=headers,
            json={"name": "External", "targetService": "https://example.com", "endpoint": "/"},
        )
        assert external_response.status_code == 400

        unknown_response = client.post(
            f"/api/labs/{lab['id']}/custom-scenarios",
            headers=headers,
            json={"name": "Unknown", "targetService": "not-in-lab", "endpoint": "/"},
        )
        assert unknown_response.status_code == 400


def test_target_app_rejects_duplicate_service_name() -> None:
    with TestClient(app) as client:
        headers = auth_headers(client)
        lab = create_lab(client, headers)
        response = client.post(
            f"/api/labs/{lab['id']}/target-apps",
            headers=headers,
            json={
                "appName": "Auth Clone",
                "serviceName": "auth-service",
                "importType": "local-service",
                "port": 8080,
            },
        )
        assert response.status_code == 409
