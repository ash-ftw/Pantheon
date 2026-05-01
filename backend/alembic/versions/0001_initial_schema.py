from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "organization_templates",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("name", sa.String(length=140), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("service_config_json", sa.JSON(), nullable=False),
        sa.Column("normal_traffic_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "attack_scenarios",
        sa.Column("id", sa.String(length=80), primary_key=True),
        sa.Column("scenario_name", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=40), nullable=False),
        sa.Column("attack_type", sa.String(length=80), nullable=False),
        sa.Column("scenario_config_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "labs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("template_id", sa.String(length=80), sa.ForeignKey("organization_templates.id"), nullable=False),
        sa.Column("lab_name", sa.String(length=180), nullable=False),
        sa.Column("namespace", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("deployment_mode", sa.String(length=40), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_labs_user_id", "labs", ["user_id"])
    op.create_index("ix_labs_namespace", "labs", ["namespace"], unique=True)

    op.create_table(
        "service_instances",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("lab_id", sa.String(length=36), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("service_name", sa.String(length=120), nullable=False),
        sa.Column("service_type", sa.String(length=40), nullable=False),
        sa.Column("kubernetes_deployment_name", sa.String(length=120), nullable=False),
        sa.Column("kubernetes_service_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("port", sa.Integer(), nullable=True),
        sa.Column("exposed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("lab_id", "service_name", name="uq_service_lab_name"),
    )
    op.create_index("ix_service_instances_lab_id", "service_instances", ["lab_id"])

    op.create_table(
        "target_applications",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("lab_id", sa.String(length=36), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("app_name", sa.String(length=140), nullable=False),
        sa.Column("service_name", sa.String(length=120), nullable=False),
        sa.Column("import_type", sa.String(length=40), nullable=False),
        sa.Column("image", sa.String(length=255), nullable=True),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("health_path", sa.String(length=240), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("internal_url", sa.String(length=255), nullable=False),
        sa.Column("safety_state", sa.String(length=40), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("lab_id", "service_name", name="uq_target_app_lab_service"),
    )
    op.create_index("ix_target_applications_lab_id", "target_applications", ["lab_id"])

    op.create_table(
        "simulation_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("lab_id", sa.String(length=36), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("scenario_id", sa.String(length=80), sa.ForeignKey("attack_scenarios.id"), nullable=False),
        sa.Column("scenario_name", sa.String(length=180), nullable=False),
        sa.Column("attack_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=False),
        sa.Column("blocked", sa.Boolean(), nullable=False),
        sa.Column("blocked_at", sa.String(length=120), nullable=True),
        sa.Column("reached_services_json", sa.JSON(), nullable=False),
        sa.Column("suspicious_event_count", sa.Integer(), nullable=False),
        sa.Column("applied_defenses_json", sa.JSON(), nullable=False),
        sa.Column("attack_path_json", sa.JSON(), nullable=False),
        sa.Column("comparison_json", sa.JSON(), nullable=True),
    )
    op.create_index("ix_simulation_runs_lab_id", "simulation_runs", ["lab_id"])

    op.create_table(
        "simulation_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("simulation_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("lab_id", sa.String(length=36), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_service", sa.String(length=120), nullable=False),
        sa.Column("target_service", sa.String(length=120), nullable=False),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("endpoint", sa.String(length=240), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.Column("payload_category", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("is_attack_simulation", sa.Boolean(), nullable=False),
        sa.Column("raw_log_json", sa.JSON(), nullable=False),
    )
    op.create_index("ix_simulation_logs_simulation_id", "simulation_logs", ["simulation_id"])
    op.create_index("ix_simulation_logs_lab_id", "simulation_logs", ["lab_id"])

    op.create_table(
        "ai_analyses",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("simulation_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False, unique=True),
        sa.Column("classification", sa.String(length=80), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("recommended_defense_categories_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "defense_recommendations",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("simulation_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("catalog_id", sa.String(length=80), nullable=False),
        sa.Column("recommendation_type", sa.String(length=80), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("defense_level", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("is_applicable", sa.Boolean(), nullable=False),
        sa.Column("already_applied", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_defense_recommendations_simulation_id", "defense_recommendations", ["simulation_id"])

    op.create_table(
        "defense_actions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("lab_id", sa.String(length=36), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("simulation_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=True),
        sa.Column("recommendation_id", sa.String(length=36), sa.ForeignKey("defense_recommendations.id"), nullable=True),
        sa.Column("catalog_id", sa.String(length=80), nullable=False),
        sa.Column("action_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("lab_id", "action_type", "status", name="uq_active_defense_action"),
    )
    op.create_index("ix_defense_actions_lab_id", "defense_actions", ["lab_id"])

    op.create_table(
        "reports",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("simulation_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False, unique=True),
        sa.Column("lab_id", sa.String(length=36), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("report_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_lab_id", "reports", ["lab_id"])


def downgrade() -> None:
    op.drop_index("ix_reports_lab_id", table_name="reports")
    op.drop_table("reports")
    op.drop_index("ix_defense_actions_lab_id", table_name="defense_actions")
    op.drop_table("defense_actions")
    op.drop_index("ix_defense_recommendations_simulation_id", table_name="defense_recommendations")
    op.drop_table("defense_recommendations")
    op.drop_table("ai_analyses")
    op.drop_index("ix_simulation_logs_lab_id", table_name="simulation_logs")
    op.drop_index("ix_simulation_logs_simulation_id", table_name="simulation_logs")
    op.drop_table("simulation_logs")
    op.drop_index("ix_simulation_runs_lab_id", table_name="simulation_runs")
    op.drop_table("simulation_runs")
    op.drop_index("ix_target_applications_lab_id", table_name="target_applications")
    op.drop_table("target_applications")
    op.drop_index("ix_service_instances_lab_id", table_name="service_instances")
    op.drop_table("service_instances")
    op.drop_index("ix_labs_namespace", table_name="labs")
    op.drop_index("ix_labs_user_id", table_name="labs")
    op.drop_table("labs")
    op.drop_table("attack_scenarios")
    op.drop_table("organization_templates")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")
