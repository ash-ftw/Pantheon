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
