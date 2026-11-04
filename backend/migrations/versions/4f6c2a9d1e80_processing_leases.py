"""Add processing leases and fencing tokens for crash recovery.

Revision ID: 4f6c2a9d1e80
Revises: 31d8a4c7e920
Create Date: 2026-11-04
"""

import sqlalchemy as sa
from alembic import op

revision = "4f6c2a9d1e80"
down_revision = "31d8a4c7e920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_processing_jobs", sa.Column("lease_expires_at", sa.Float(), nullable=True))
    op.add_column("document_processing_jobs", sa.Column("lease_token", sa.Uuid(), nullable=True))
    op.create_index(
        "ix_document_processing_jobs_status_lease",
        "document_processing_jobs",
        ["status", "lease_expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_processing_jobs_status_lease", table_name="document_processing_jobs")
    op.drop_column("document_processing_jobs", "lease_token")
    op.drop_column("document_processing_jobs", "lease_expires_at")
