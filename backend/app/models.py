from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def uuid_str() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="Student", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    labs: Mapped[list["Lab"]] = relationship(back_populates="owner")


class OrganizationTemplate(Base):
    __tablename__ = "organization_templates"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(140), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    service_config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    normal_traffic_json: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    labs: Mapped[list["Lab"]] = relationship(back_populates="template")


class AttackScenario(Base):
    __tablename__ = "attack_scenarios"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    scenario_name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    difficulty: Mapped[str] = mapped_column(String(40), nullable=False)
    attack_type: Mapped[str] = mapped_column(String(80), nullable=False)
    scenario_config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    simulations: Mapped[list["SimulationRun"]] = relationship(back_populates="scenario")


class Lab(Base):
    __tablename__ = "labs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True, nullable=False)
    template_id: Mapped[str] = mapped_column(String(80), ForeignKey("organization_templates.id"), nullable=False)
    lab_name: Mapped[str] = mapped_column(String(180), nullable=False)
    namespace: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Provisioning", nullable=False)
    deployment_mode: Mapped[str] = mapped_column(String(40), default="dry-run", nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped["User"] = relationship(back_populates="labs")
    template: Mapped["OrganizationTemplate"] = relationship(back_populates="labs")
    services: Mapped[list["ServiceInstance"]] = relationship(
        back_populates="lab",
        cascade="all, delete-orphan",
        order_by="ServiceInstance.service_name",
    )
    simulations: Mapped[list["SimulationRun"]] = relationship(
        back_populates="lab",
        cascade="all, delete-orphan",
        order_by="SimulationRun.started_at",
    )
    defense_actions: Mapped[list["DefenseAction"]] = relationship(back_populates="lab", cascade="all, delete-orphan")


class ServiceInstance(Base):
    __tablename__ = "service_instances"
    __table_args__ = (UniqueConstraint("lab_id", "service_name", name="uq_service_lab_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    lab_id: Mapped[str] = mapped_column(String(36), ForeignKey("labs.id"), index=True, nullable=False)
    service_name: Mapped[str] = mapped_column(String(120), nullable=False)
    service_type: Mapped[str] = mapped_column(String(40), nullable=False)
    kubernetes_deployment_name: Mapped[str] = mapped_column(String(120), nullable=False)
    kubernetes_service_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Pending", nullable=False)
    port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exposed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    lab: Mapped["Lab"] = relationship(back_populates="services")


class SimulationRun(Base):
    __tablename__ = "simulation_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    lab_id: Mapped[str] = mapped_column(String(36), ForeignKey("labs.id"), index=True, nullable=False)
    scenario_id: Mapped[str] = mapped_column(String(80), ForeignKey("attack_scenarios.id"), nullable=False)
    scenario_name: Mapped[str] = mapped_column(String(180), nullable=False)
    attack_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Completed", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    result_summary: Mapped[str] = mapped_column(Text, nullable=False)
    blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked_at: Mapped[str | None] = mapped_column(String(120), nullable=True)
    reached_services_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    suspicious_event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    applied_defenses_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    attack_path_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    comparison_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    lab: Mapped["Lab"] = relationship(back_populates="simulations")
    scenario: Mapped["AttackScenario"] = relationship(back_populates="simulations")
    logs: Mapped[list["SimulationLog"]] = relationship(
        back_populates="simulation",
        cascade="all, delete-orphan",
        order_by="SimulationLog.timestamp",
    )
    ai_analysis: Mapped["AIAnalysis | None"] = relationship(
        back_populates="simulation",
        cascade="all, delete-orphan",
        uselist=False,
    )
    recommendations: Mapped[list["DefenseRecommendation"]] = relationship(
        back_populates="simulation",
        cascade="all, delete-orphan",
        order_by="DefenseRecommendation.priority",
    )
    report: Mapped["Report | None"] = relationship(back_populates="simulation", cascade="all, delete-orphan", uselist=False)


class SimulationLog(Base):
    __tablename__ = "simulation_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    simulation_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulation_runs.id"), index=True, nullable=False)
    lab_id: Mapped[str] = mapped_column(String(36), ForeignKey("labs.id"), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    source_service: Mapped[str] = mapped_column(String(120), nullable=False)
    target_service: Mapped[str] = mapped_column(String(120), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(240), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    request_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    payload_category: Mapped[str] = mapped_column(String(80), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), default="Info", nullable=False)
    is_attack_simulation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    raw_log_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    simulation: Mapped["SimulationRun"] = relationship(back_populates="logs")


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    simulation_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulation_runs.id"), unique=True, nullable=False)
    classification: Mapped[str] = mapped_column(String(80), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_defense_categories_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    simulation: Mapped["SimulationRun"] = relationship(back_populates="ai_analysis")


class DefenseRecommendation(Base):
    __tablename__ = "defense_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    simulation_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulation_runs.id"), index=True, nullable=False)
    catalog_id: Mapped[str] = mapped_column(String(80), nullable=False)
    recommendation_type: Mapped[str] = mapped_column(String(80), nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    defense_level: Mapped[str] = mapped_column(String(40), nullable=False)
    priority: Mapped[str] = mapped_column(String(32), nullable=False)
    is_applicable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    already_applied: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    simulation: Mapped["SimulationRun"] = relationship(back_populates="recommendations")


class DefenseAction(Base):
    __tablename__ = "defense_actions"
    __table_args__ = (UniqueConstraint("lab_id", "action_type", "status", name="uq_active_defense_action"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    lab_id: Mapped[str] = mapped_column(String(36), ForeignKey("labs.id"), index=True, nullable=False)
    simulation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("simulation_runs.id"), nullable=True)
    recommendation_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("defense_recommendations.id"), nullable=True)
    catalog_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Applied", nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    details_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    lab: Mapped["Lab"] = relationship(back_populates="defense_actions")


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid_str)
    simulation_id: Mapped[str] = mapped_column(String(36), ForeignKey("simulation_runs.id"), unique=True, nullable=False)
    lab_id: Mapped[str] = mapped_column(String(36), ForeignKey("labs.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    report_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    simulation: Mapped["SimulationRun"] = relationship(back_populates="report")
