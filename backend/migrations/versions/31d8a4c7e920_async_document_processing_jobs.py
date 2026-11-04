"""Add durable academic document processing jobs.

Revision ID: 31d8a4c7e920
Revises: 8c3f7a1d9b20
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op

revision = "31d8a4c7e920"
down_revision = "8c3f7a1d9b20"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "document_extractions",
        sa.Column("quality_report", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_table(
        "document_processing_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "queued", "processing", "completed", "failed",
                name="extractionjobstatus", native_enum=False, length=24,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.Float(), nullable=True),
        sa.Column("finished_at", sa.Float(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False,
        ),
        sa.ForeignKeyConstraint(["version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", name="uq_document_processing_job_version"),
    )
    op.create_index(
        "ix_document_processing_jobs_status_created",
        "document_processing_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_processing_jobs_status_created", table_name="document_processing_jobs")
    op.drop_table("document_processing_jobs")
    op.drop_column("document_extractions", "quality_report")
