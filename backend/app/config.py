from __future__ import annotations

import os
from dataclasses import dataclass


def _csv_env(name: str, default: str) -> list[str]:
    value = os.getenv(name, default)
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    app_name: str = "Pantheon API"
    api_prefix: str = "/api"
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://pantheon:pantheon@localhost:5432/pantheon",
    )
    secret_key: str = os.getenv("SECRET_KEY", "change-this-dev-secret")
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
    kubernetes_mode: str = os.getenv("KUBERNETES_MODE", "dry-run").lower()
    kubeconfig: str | None = os.getenv("KUBECONFIG") or None
    namespace_prefix: str = os.getenv("KUBERNETES_NAMESPACE_PREFIX", "pantheon-lab")
    service_image: str = os.getenv(
        "KUBERNETES_SERVICE_IMAGE",
        "pantheon-fake-service:latest",
    )
    runner_image: str = os.getenv("KUBERNETES_RUNNER_IMAGE", "pantheon-runner:latest")
    runner_image_pull_policy: str = os.getenv("KUBERNETES_RUNNER_IMAGE_PULL_POLICY", "IfNotPresent")
    job_timeout_seconds: int = int(os.getenv("KUBERNETES_JOB_TIMEOUT_SECONDS", "120"))
    auto_create_tables: bool = os.getenv("PANTHEON_AUTO_CREATE_TABLES", "true").lower() in {"1", "true", "yes", "on"}
    frontend_origins: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "frontend_origins",
            _csv_env(
                "KUBERNETES_FRONTEND_ORIGINS",
                "http://localhost:8090,http://localhost:5173,http://localhost:3000",
            ),
        )


settings = Settings()
