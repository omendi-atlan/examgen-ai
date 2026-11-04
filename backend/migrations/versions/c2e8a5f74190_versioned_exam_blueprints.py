"""Create versioned examination blueprint tables."""

import sqlalchemy as sa
from alembic import op

revision = "c2e8a5f74190"
down_revision = "9b2d6f4a1c80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exam_blueprints",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("current_version_number >= 0", name="ck_exam_blueprint_current_version"),
    )
    op.create_index(
        "ix_exam_blueprints_workspace_updated",
        "exam_blueprints",
        ["workspace_id", "updated_at"],
    )
    op.create_table(
        "exam_blueprint_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("blueprint_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("total_marks", sa.Integer(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("cognitive_distribution", sa.JSON(), nullable=False),
        sa.Column("difficulty_distribution", sa.JSON(), nullable=False),
        sa.Column("question_type_distribution", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["blueprint_id"], ["exam_blueprints.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("blueprint_id", "version_number", name="uq_blueprint_version_number"),
        sa.CheckConstraint("version_number > 0", name="ck_blueprint_version_number_positive"),
        sa.CheckConstraint("duration_minutes BETWEEN 1 AND 600", name="ck_blueprint_duration_range"),
        sa.CheckConstraint("total_marks BETWEEN 1 AND 1000", name="ck_blueprint_total_marks_range"),
        sa.CheckConstraint("question_count BETWEEN 1 AND 200", name="ck_blueprint_question_count_range"),
        sa.CheckConstraint("question_count <= total_marks", name="ck_blueprint_question_count_marks"),
        sa.CheckConstraint("status IN ('draft', 'approved')", name="ck_blueprint_version_status"),
    )
    op.create_index(
        "ix_blueprint_versions_subject_created",
        "exam_blueprint_versions",
        ["subject_id", "created_at"],
    )
    op.create_table(
        "blueprint_topic_weights",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("version_id", sa.Uuid(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("target_marks", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["exam_blueprint_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "topic_id", name="uq_blueprint_version_topic_weight"),
        sa.CheckConstraint("target_marks > 0", name="ck_blueprint_topic_target_marks_positive"),
    )
    op.create_index(
        "ix_blueprint_topic_weights_topic",
        "blueprint_topic_weights",
        ["topic_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_blueprint_topic_weights_topic", table_name="blueprint_topic_weights")
    op.drop_table("blueprint_topic_weights")
    op.drop_index("ix_blueprint_versions_subject_created", table_name="exam_blueprint_versions")
    op.drop_table("exam_blueprint_versions")
    op.drop_index("ix_exam_blueprints_workspace_updated", table_name="exam_blueprints")
    op.drop_table("exam_blueprints")
