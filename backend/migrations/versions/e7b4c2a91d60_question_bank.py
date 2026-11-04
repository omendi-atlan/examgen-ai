"""Create immutable question bank identities and versions."""

import sqlalchemy as sa
from alembic import op

revision = "e7b4c2a91d60"
down_revision = "c2e8a5f74190"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("current_version_number >= 0", name="ck_question_current_version"),
    )
    op.create_index(
        "ix_questions_workspace_subject_owner",
        "questions",
        ["workspace_id", "subject_id", "created_by"],
    )
    op.create_table(
        "question_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=True),
        sa.Column("learning_outcome_id", sa.Uuid(), nullable=True),
        sa.Column("question_type", sa.String(length=40), nullable=False),
        sa.Column("stem", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.Column("correct_answer", sa.JSON(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("marks", sa.Integer(), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.Column("cognitive_level", sa.String(length=16), nullable=False),
        sa.Column("source_citations", sa.JSON(), nullable=False),
        sa.Column("generation_model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=40), nullable=False),
        sa.Column("review_status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["learning_outcome_id"], ["learning_outcomes.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "version_number", name="uq_question_version_number"),
        sa.CheckConstraint("version_number > 0", name="ck_question_version_positive"),
        sa.CheckConstraint("marks BETWEEN 1 AND 100", name="ck_question_marks_range"),
        sa.CheckConstraint("review_status IN ('draft', 'approved', 'rejected')", name="ck_question_review_status"),
        sa.CheckConstraint("question_type IN ('multiple_choice', 'multiple_select', 'true_false', 'fill_blank', 'short_answer', 'long_answer', 'numeric', 'matching', 'ordering', 'programming', 'diagram_interpretation', 'diagram_construction')", name="ck_question_type"),
        sa.CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="ck_question_difficulty"),
        sa.CheckConstraint("cognitive_level IN ('remember', 'understand', 'apply', 'analyze', 'evaluate', 'create')", name="ck_question_cognitive_level"),
    )
    op.create_index("ix_question_versions_topic_status", "question_versions", ["topic_id", "review_status"])
    op.create_index("ix_question_versions_outcome", "question_versions", ["learning_outcome_id"])


def downgrade() -> None:
    op.drop_index("ix_question_versions_outcome", table_name="question_versions")
    op.drop_index("ix_question_versions_topic_status", table_name="question_versions")
    op.drop_table("question_versions")
    op.drop_index("ix_questions_workspace_subject_owner", table_name="questions")
    op.drop_table("questions")
