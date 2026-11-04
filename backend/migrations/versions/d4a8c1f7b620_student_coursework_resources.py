"""Bind academic resources to subjects and add explicit sharing policy.

Revision ID: d4a8c1f7b620
Revises: 9b2d6f4a1c80
Create Date: 2026-11-04
"""
import sqlalchemy as sa
from alembic import op

revision = "d4a8c1f7b620"
down_revision = "9b2d6f4a1c80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "subjects",
        sa.Column("resource_sharing_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("academic_documents", sa.Column("subject_id", sa.Uuid(), nullable=True))
    op.add_column(
        "academic_documents",
        sa.Column("visibility", sa.String(length=16), nullable=False, server_default="private"),
    )
    op.create_foreign_key(
        "fk_academic_documents_subject_id_subjects",
        "academic_documents",
        "subjects",
        ["subject_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_academic_documents_visibility",
        "academic_documents",
        "visibility IN ('private', 'cohort')",
    )
    op.create_index(
        "ix_academic_documents_subject_owner",
        "academic_documents",
        ["workspace_id", "subject_id", "created_by"],
    )


def downgrade() -> None:
    op.drop_index("ix_academic_documents_subject_owner", table_name="academic_documents")
    op.drop_constraint("ck_academic_documents_visibility", "academic_documents", type_="check")
    op.drop_constraint(
        "fk_academic_documents_subject_id_subjects",
        "academic_documents",
        type_="foreignkey",
    )
    op.drop_column("academic_documents", "visibility")
    op.drop_column("academic_documents", "subject_id")
    op.drop_column("subjects", "resource_sharing_enabled")
