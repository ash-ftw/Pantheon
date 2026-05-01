from __future__ import annotations

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

from app.main import app  # noqa: E402


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
