from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_simulation_jobs"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "simulation_jobs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("simulation_id", sa.String(length=36), sa.ForeignKey("simulation_runs.id"), nullable=False),
        sa.Column("lab_id", sa.String(length=36), sa.ForeignKey("labs.id"), nullable=False),
        sa.Column("namespace", sa.String(length=120), nullable=False),
        sa.Column("job_name", sa.String(length=120), nullable=False),
        sa.Column("job_type", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("details_json", sa.JSON(), nullable=False),
        sa.UniqueConstraint("simulation_id", "job_name", name="uq_simulation_job_name"),
    )
    op.create_index("ix_simulation_jobs_simulation_id", "simulation_jobs", ["simulation_id"])
    op.create_index("ix_simulation_jobs_lab_id", "simulation_jobs", ["lab_id"])


def downgrade() -> None:
    op.drop_index("ix_simulation_jobs_lab_id", table_name="simulation_jobs")
    op.drop_index("ix_simulation_jobs_simulation_id", table_name="simulation_jobs")
    op.drop_table("simulation_jobs")
