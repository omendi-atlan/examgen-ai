"""Create reusable, versioned question bank with source provenance."""

import sqlalchemy as sa
from alembic import op

revision = "f7c2a91d4e60"
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
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("visibility IN ('private', 'cohort')", name="ck_question_visibility"),
        sa.CheckConstraint("current_version_number >= 0", name="ck_question_current_version"),
    )
    op.create_index(
        "ix_questions_workspace_subject_updated",
        "questions",
        ["workspace_id", "subject_id", "updated_at"],
    )
    op.create_index("ix_questions_subject_owner", "questions", ["subject_id", "created_by"])

    op.create_table(
        "question_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Uuid(), nullable=False),
        sa.Column("learning_outcome_id", sa.Uuid(), nullable=False),
        sa.Column("question_type", sa.String(length=32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("marks", sa.Integer(), nullable=False),
        sa.Column("cognitive_level", sa.String(length=16), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=False),
        sa.Column("response_schema", sa.JSON(), nullable=False),
        sa.Column("answer_key", sa.JSON(), nullable=True),
        sa.Column("model_answer", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("rubric", sa.JSON(), nullable=True),
        sa.Column("visual_requirement", sa.JSON(), nullable=True),
        sa.Column("generation_method", sa.String(length=16), nullable=False),
        sa.Column("generation_model", sa.String(length=120), nullable=True),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("approved_by", sa.Uuid(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["learning_outcome_id"], ["learning_outcomes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "version_number", name="uq_question_version_number"),
        sa.CheckConstraint("version_number > 0", name="ck_question_version_number_positive"),
        sa.CheckConstraint("marks BETWEEN 1 AND 1000", name="ck_question_marks_range"),
        sa.CheckConstraint(
            "question_type IN ('multiple_choice', 'multiple_select', 'true_false', "
            "'fill_blank', 'short_answer', 'long_answer', 'numeric', 'matching', "
            "'ordering', 'programming', 'diagram_interpretation', 'diagram_construction')",
            name="ck_question_type",
        ),
        sa.CheckConstraint(
            "cognitive_level IN ('remember', 'understand', 'apply', 'analyze', 'evaluate', 'create')",
            name="ck_question_cognitive_level",
        ),
        sa.CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="ck_question_difficulty"),
        sa.CheckConstraint(
            "status IN ('draft', 'approved', 'rejected', 'retired')",
            name="ck_question_version_status",
        ),
        sa.CheckConstraint(
            "generation_method IN ('manual', 'ai')", name="ck_question_generation_method"
        ),
    )
    op.create_index(
        "ix_question_versions_topic_status", "question_versions", ["topic_id", "status"]
    )
    op.create_index(
        "ix_question_versions_outcome_status",
        "question_versions",
        ["learning_outcome_id", "status"],
    )

    op.create_table(
        "question_source_citations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("question_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_segment_id", sa.Uuid(), nullable=False),
        sa.Column("source_version_id", sa.Uuid(), nullable=False),
        sa.Column("source_locator", sa.String(length=120), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.Column("relevance_note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(
            ["question_version_id"], ["question_versions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["source_segment_id"], ["document_text_segments.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["source_version_id"], ["document_versions.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "question_version_id", "source_segment_id", name="uq_question_source_segment"
        ),
    )
    op.create_index(
        "ix_question_source_citations_segment",
        "question_source_citations",
        ["source_segment_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_question_source_citations_segment", table_name="question_source_citations")
    op.drop_table("question_source_citations")
    op.drop_index("ix_question_versions_outcome_status", table_name="question_versions")
    op.drop_index("ix_question_versions_topic_status", table_name="question_versions")
    op.drop_table("question_versions")
    op.drop_index("ix_questions_subject_owner", table_name="questions")
    op.drop_index("ix_questions_workspace_subject_updated", table_name="questions")
    op.drop_table("questions")
