"""Create visual intelligence and moderation tables."""

import sqlalchemy as sa
from alembic import op

revision = "a3f9d2c71b48"
down_revision = "f2c8a6d1b930"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visual_requirement_assessments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("blueprint_version_id", sa.Uuid(), nullable=False),
        sa.Column("analyser_version", sa.String(length=40), nullable=False),
        sa.Column("essential_count", sa.Integer(), nullable=False),
        sa.Column("beneficial_count", sa.Integer(), nullable=False),
        sa.Column("unnecessary_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blueprint_version_id"], ["exam_blueprint_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blueprint_version_id", name="uq_visual_assessment_blueprint_version"),
    )
    op.create_index(
        "ix_visual_assessments_workspace",
        "visual_requirement_assessments",
        ["workspace_id", "created_at"],
    )
    op.create_table(
        "visual_requirement_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("assessment_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("topic_name", sa.String(length=160), nullable=False),
        sa.Column("requirement_level", sa.String(length=16), nullable=False),
        sa.Column("recommended_kind", sa.String(length=24), nullable=True),
        sa.Column("proposed_title", sa.String(length=240), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["assessment_id"], ["visual_requirement_assessments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("assessment_id", "topic_id", name="uq_visual_requirement_topic"),
        sa.CheckConstraint(
            "requirement_level IN ('essential', 'beneficial', 'unnecessary')",
            name="ck_visual_requirement_level",
        ),
    )
    op.create_index("ix_visual_requirement_items_level", "visual_requirement_items", ["requirement_level"])
    op.create_table(
        "visual_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("blueprint_version_id", sa.Uuid(), nullable=False),
        sa.Column("requirement_item_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blueprint_version_id"], ["exam_blueprint_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requirement_item_id"], ["visual_requirement_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blueprint_version_id", "fingerprint", name="uq_visual_asset_fingerprint"),
        sa.CheckConstraint("current_version_number >= 0", name="ck_visual_asset_current_version"),
    )
    op.create_index("ix_visual_assets_workspace_subject", "visual_assets", ["workspace_id", "subject_id"])
    op.create_table(
        "visual_asset_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("diagram_kind", sa.String(length=24), nullable=False),
        sa.Column("spec", sa.JSON(), nullable=False),
        sa.Column("svg_markup", sa.Text(), nullable=False),
        sa.Column("validation_report", sa.JSON(), nullable=False),
        sa.Column("alt_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["visual_assets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("asset_id", "version_number", name="uq_visual_asset_version_number"),
        sa.CheckConstraint("version_number > 0", name="ck_visual_asset_version_positive"),
        sa.CheckConstraint("status IN ('draft', 'approved', 'rejected')", name="ck_visual_asset_status"),
    )
    op.create_index("ix_visual_asset_versions_status", "visual_asset_versions", ["status"])
    op.create_table(
        "visual_asset_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_version_id", sa.Uuid(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["asset_version_id"], ["visual_asset_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("decision IN ('approved', 'rejected')", name="ck_visual_asset_decision"),
    )
    op.create_index(
        "ix_visual_asset_decisions_version_created",
        "visual_asset_decisions",
        ["asset_version_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_visual_asset_decisions_version_created", table_name="visual_asset_decisions")
    op.drop_table("visual_asset_decisions")
    op.drop_index("ix_visual_asset_versions_status", table_name="visual_asset_versions")
    op.drop_table("visual_asset_versions")
    op.drop_index("ix_visual_assets_workspace_subject", table_name="visual_assets")
    op.drop_table("visual_assets")
    op.drop_index("ix_visual_requirement_items_level", table_name="visual_requirement_items")
    op.drop_table("visual_requirement_items")
    op.drop_index("ix_visual_assessments_workspace", table_name="visual_requirement_assessments")
    op.drop_table("visual_requirement_assessments")
