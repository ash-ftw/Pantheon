from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class UserCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=128)
    role: str = "Student"


class UserLogin(BaseModel):
    email: str
    password: str


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    email: str
    role: str
    created_at: datetime
    updated_at: datetime


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    user: UserPublic


class TemplateOut(BaseModel):
    id: str
    name: str
    description: str
    services: list[dict[str, Any]]
    normalTraffic: list[str]


class ScenarioOut(BaseModel):
    id: str
    name: str
    description: str
    difficulty: str
    attackType: str
    allowedTemplateIds: list[str]
    targetServices: list[str]
    defaultRisk: str
    isCustom: bool = False
    targetLabId: str | None = None


class LabCreate(BaseModel):
    lab_name: str | None = None
    labName: str | None = None
    template_id: str | None = None
    templateId: str | None = None


class ServiceInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    labId: str
    serviceName: str
    serviceType: str
    kubernetesDeploymentName: str
    kubernetesServiceName: str
    status: str
    port: int | None
    exposed: bool
    createdAt: datetime


class TargetApplicationCreate(BaseModel):
    app_name: str | None = None
    appName: str | None = None
    service_name: str | None = None
    serviceName: str | None = None
    import_type: str | None = None
    importType: str | None = None
    image: str | None = None
    port: int = Field(default=8080, ge=1, le=65535)
    health_path: str | None = None
    healthPath: str | None = None
    manifest: str | None = None
    local_url: str | None = None
    localUrl: str | None = None
    normal_paths: list[str] | None = None
    normalPaths: list[str] | None = None


class TargetApplicationOut(BaseModel):
    id: str
    labId: str
    appName: str
    serviceName: str
    importType: str
    image: str | None
    port: int
    healthPath: str
    status: str
    internalUrl: str
    safetyState: str
    manifestJson: dict[str, Any]
    createdAt: datetime


class CustomScenarioCreate(BaseModel):
    name: str = Field(default="Custom Web App Probe", min_length=1, max_length=180)
    attack_type: str | None = None
    attackType: str | None = None
    target_service: str | None = None
    targetService: str | None = None
    method: str = "GET"
    endpoint: str = "/"
    payload_category: str | None = None
    payloadCategory: str | None = None
    request_count: int | None = Field(default=None, ge=1, le=100)
    requestCount: int | None = Field(default=None, ge=1, le=100)
    risk_level: str | None = None
    riskLevel: str | None = None


class LabOut(BaseModel):
    id: str
    userId: str
    templateId: str
    labName: str
    namespace: str
    status: str
    deploymentMode: str
    errorMessage: str | None
    createdAt: datetime
    deletedAt: datetime | None
    template: TemplateOut
    services: list[ServiceInstanceOut]
    targetApplications: list[TargetApplicationOut] = []
    activeDefenses: list[dict[str, Any]] = []
    latestSimulation: dict[str, Any] | None = None


class KubernetesResourceResult(BaseModel):
    kind: str
    name: str
    status: str
    message: str | None = None


class SimulationCreate(BaseModel):
    scenario_id: str | None = None
    scenarioId: str | None = None


class DefenseApply(BaseModel):
    defense_ids: list[str] | None = None
    defense_id: str | None = None
    catalogId: str | None = None
    simulation_id: str | None = None
    simulationId: str | None = None
    recommendation_id: str | None = None
    recommendationId: str | None = None
