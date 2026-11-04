"""Create immutable practice papers and persisted student attempts."""

import sqlalchemy as sa
from alembic import op

revision = "a6d8f03c91b2"
down_revision = "f7c2a91d4e60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exam_papers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("blueprint_version_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column("visibility", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("current_version_number", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["blueprint_version_id"], ["exam_blueprint_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("visibility IN ('private', 'cohort')", name="ck_exam_paper_visibility"),
        sa.CheckConstraint("mode IN ('practice', 'simulation')", name="ck_exam_paper_mode"),
    )
    op.create_index("ix_exam_papers_workspace_subject", "exam_papers", ["workspace_id", "subject_id"])

    op.create_table(
        "exam_paper_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_id", sa.Uuid(), nullable=False),
        sa.Column("blueprint_version_id", sa.Uuid(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("total_marks", sa.Integer(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["exam_papers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["blueprint_version_id"], ["exam_blueprint_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_id", "version_number", name="uq_exam_paper_version"),
        sa.CheckConstraint("version_number > 0", name="ck_exam_paper_version_positive"),
        sa.CheckConstraint("duration_minutes BETWEEN 1 AND 600", name="ck_exam_duration_range"),
        sa.CheckConstraint("total_marks > 0", name="ck_exam_total_marks_positive"),
        sa.CheckConstraint("question_count > 0", name="ck_exam_question_count_positive"),
        sa.CheckConstraint("status IN ('published', 'retired')", name="ck_exam_paper_version_status"),
    )
    op.create_index("ix_exam_paper_versions_blueprint", "exam_paper_versions", ["blueprint_version_id"])

    op.create_table(
        "exam_paper_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_version_id", sa.Uuid(), nullable=False),
        sa.Column("question_version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("marks", sa.Integer(), nullable=False),
        sa.Column("question_snapshot", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["paper_version_id"], ["exam_paper_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_version_id"], ["question_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paper_version_id", "ordinal", name="uq_exam_paper_question_ordinal"),
        sa.UniqueConstraint("paper_version_id", "question_version_id", name="uq_exam_paper_question_version"),
        sa.CheckConstraint("ordinal > 0", name="ck_exam_paper_question_ordinal"),
        sa.CheckConstraint("marks > 0", name="ck_exam_paper_question_marks"),
    )
    op.create_index(
        "ix_exam_paper_questions_question_version",
        "exam_paper_questions",
        ["question_version_id"],
    )

    op.create_table(
        "exam_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("paper_version_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_saved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["paper_version_id"], ["exam_paper_versions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["candidate_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('in_progress', 'submitted', 'expired')",
            name="ck_exam_attempt_status",
        ),
    )
    op.create_index("ix_exam_attempt_user_status", "exam_attempts", ["candidate_user_id", "status"])
    op.create_index("ix_exam_attempt_deadline_status", "exam_attempts", ["deadline_at", "status"])

    op.create_table(
        "attempt_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("paper_question_id", sa.Uuid(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["exam_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_question_id"], ["exam_paper_questions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", "paper_question_id", name="uq_attempt_response_question"),
        sa.CheckConstraint("revision > 0", name="ck_attempt_response_revision"),
    )
    op.create_index("ix_attempt_responses_attempt_saved", "attempt_responses", ["attempt_id", "saved_at"])

    op.create_table(
        "attempt_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("response_snapshot", sa.JSON(), nullable=False),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["exam_attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", name="uq_attempt_submission_once"),
    )
    op.create_index("ix_attempt_submissions_submitted_at", "attempt_submissions", ["submitted_at"])

    op.create_table(
        "attempt_marks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("paper_question_id", sa.Uuid(), nullable=False),
        sa.Column("awarded_marks", sa.Float(), nullable=True),
        sa.Column("max_marks", sa.Integer(), nullable=False),
        sa.Column("marking_method", sa.String(length=16), nullable=False),
        sa.Column("feedback", sa.JSON(), nullable=False),
        sa.Column("marked_by", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["submission_id"], ["attempt_submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["paper_question_id"], ["exam_paper_questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["marked_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "paper_question_id", name="uq_attempt_mark_question"),
        sa.CheckConstraint("max_marks > 0", name="ck_attempt_mark_max_positive"),
        sa.CheckConstraint(
            "awarded_marks IS NULL OR (awarded_marks >= 0 AND awarded_marks <= max_marks)",
            name="ck_attempt_mark_awarded_range",
        ),
        sa.CheckConstraint("marking_method IN ('objective', 'manual')", name="ck_attempt_mark_method"),
    )


def downgrade() -> None:
    op.drop_table("attempt_marks")
    op.drop_index("ix_attempt_submissions_submitted_at", table_name="attempt_submissions")
    op.drop_table("attempt_submissions")
    op.drop_index("ix_attempt_responses_attempt_saved", table_name="attempt_responses")
    op.drop_table("attempt_responses")
    op.drop_index("ix_exam_attempt_deadline_status", table_name="exam_attempts")
    op.drop_index("ix_exam_attempt_user_status", table_name="exam_attempts")
    op.drop_table("exam_attempts")
    op.drop_index("ix_exam_paper_questions_question_version", table_name="exam_paper_questions")
    op.drop_table("exam_paper_questions")
    op.drop_index("ix_exam_paper_versions_blueprint", table_name="exam_paper_versions")
    op.drop_table("exam_paper_versions")
    op.drop_index("ix_exam_papers_workspace_subject", table_name="exam_papers")
    op.drop_table("exam_papers")
