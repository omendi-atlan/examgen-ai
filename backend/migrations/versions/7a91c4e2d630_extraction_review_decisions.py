"""Add append-only examiner decisions for academic extraction review."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "7a91c4e2d630"
down_revision = "4f6c2a9d1e80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "document_extraction_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("reviewed_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("decision IN ('accepted', 'rejected')", name="ck_extraction_review_decision"),
    )
    op.create_index(
        "ix_extraction_reviews_version_created",
        "document_extraction_reviews",
        ["version_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_extraction_reviews_version_created", table_name="document_extraction_reviews")
    op.drop_table("document_extraction_reviews")
