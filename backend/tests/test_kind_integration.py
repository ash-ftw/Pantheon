from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.services.kubernetes_service import KubernetesService  # noqa: E402


pytestmark = pytest.mark.skipif(
    os.getenv("PANTHEON_RUN_KIND_TESTS") != "true",
    reason="Kind integration tests require PANTHEON_RUN_KIND_TESTS=true and a configured Kubernetes cluster.",
)


def test_real_kubernetes_lab_status_and_observed_runner_logs() -> None:
    app_settings = Settings(
        kubernetes_mode="real",
        kubeconfig=os.getenv("KUBECONFIG") or None,
        namespace_prefix="pantheon-ci",
        service_image=os.getenv("KUBERNETES_SERVICE_IMAGE", "pantheon-fake-service:latest"),
        runner_image=os.getenv("KUBERNETES_RUNNER_IMAGE", "pantheon-runner:latest"),
        runner_image_pull_policy=os.getenv("KUBERNETES_RUNNER_IMAGE_PULL_POLICY", "IfNotPresent"),
        job_timeout_seconds=int(os.getenv("KUBERNETES_JOB_TIMEOUT_SECONDS", "90")),
    )
    kubernetes = KubernetesService(app_settings)
    namespace = f"pantheon-ci-{uuid4().hex[:8]}"
    services = [
        {"name": "frontend-service", "type": "frontend", "port": 8080, "exposed": True},
        {"name": "auth-service", "type": "auth", "port": 8080, "exposed": False},
    ]
    scenario_config = {
        "steps": [
            {
                "source": "attack-pod",
                "target": "auth-service",
                "method": "POST",
                "endpoint": "/login",
                "payload_category": "credential_attempt",
                "event_type": "failed_login",
                "status_code": 401,
                "action_type": "HTTP_REQUEST_PATTERN",
                "count": 2,
            }
        ]
    }

    try:
        results = kubernetes.create_lab(namespace, services)
        assert any(item.kind == "Namespace" and item.status in {"Created", "Exists"} for item in results)

        status = _wait_until_ready(kubernetes, namespace, services)
        assert status["summary"]["allReady"] is True
        assert status["summary"]["readyServices"] == len(services)

        records = kubernetes.run_simulation_jobs(
            namespace=namespace,
            simulation_id=f"sim-{uuid4().hex[:8]}",
            services=services,
            scenario_config=scenario_config,
            normal_traffic=["GET /health", "GET /"],
        )
        assert any(item["raw_log_json"].get("observed_source") == "kubernetes_api" for item in records)
        assert any(item["raw_log_json"].get("observed_source") == "kubernetes_job_log" for item in records)
        assert any(item["raw_log_json"].get("observed_source") == "kubernetes_service_log" for item in records)
        assert any(item["is_attack_simulation"] for item in records)
    finally:
        try:
            kubernetes.delete_lab(namespace)
        except Exception:
            pass


def _wait_until_ready(
    kubernetes: KubernetesService,
    namespace: str,
    services: list[dict],
    timeout_seconds: int = 90,
) -> dict:
    deadline = time.time() + timeout_seconds
    last_status: dict | None = None
    while time.time() < deadline:
        last_status = kubernetes.get_lab_status(namespace, services)
        if last_status["summary"]["allReady"]:
            return last_status
        if last_status["summary"]["failedServices"]:
            pytest.fail(f"Kubernetes lab reported failed services: {last_status}")
        time.sleep(2)
    pytest.fail(f"Kubernetes lab did not become ready: {last_status}")
