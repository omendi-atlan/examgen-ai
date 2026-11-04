"""Create immutable practice exam definitions and durable attempts."""

import sqlalchemy as sa
from alembic import op

revision = "f2c8a6d1b930"
down_revision = "e7b4c2a91d60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "practice_exams",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("subject_id", sa.Uuid(), nullable=False),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("total_marks", sa.Integer(), nullable=False),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_id"], ["subjects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("duration_minutes BETWEEN 1 AND 360", name="ck_practice_exam_duration"),
        sa.CheckConstraint("total_marks BETWEEN 1 AND 1000", name="ck_practice_exam_marks"),
        sa.CheckConstraint("question_count BETWEEN 1 AND 100", name="ck_practice_exam_question_count"),
    )
    op.create_index(
        "ix_practice_exams_owner_subject",
        "practice_exams",
        ["workspace_id", "subject_id", "created_by"],
    )
    op.create_table(
        "practice_exam_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("question_version_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("marks", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["practice_exams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_version_id"], ["question_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_id", "ordinal", name="uq_practice_exam_question_ordinal"),
        sa.UniqueConstraint("exam_id", "question_version_id", name="uq_practice_exam_question_version"),
        sa.CheckConstraint("ordinal > 0", name="ck_practice_exam_question_ordinal"),
        sa.CheckConstraint("marks > 0", name="ck_practice_exam_question_marks"),
    )
    op.create_table(
        "practice_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exam_id", sa.Uuid(), nullable=False),
        sa.Column("student_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("awarded_marks", sa.Integer(), nullable=False),
        sa.Column("pending_review_count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["practice_exams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('in_progress', 'submitted', 'expired')", name="ck_practice_attempt_status"),
    )
    op.create_index("ix_practice_attempts_owner_status", "practice_attempts", ["student_id", "status"])
    op.create_table(
        "practice_attempt_responses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("exam_question_id", sa.Uuid(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column("awarded_marks", sa.Integer(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=True),
        sa.Column("marking_status", sa.String(length=24), nullable=False),
        sa.Column("saved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["attempt_id"], ["practice_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exam_question_id"], ["practice_exam_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", "exam_question_id", name="uq_attempt_exam_question_response"),
    )
    op.create_index("ix_attempt_responses_attempt", "practice_attempt_responses", ["attempt_id"])


def downgrade() -> None:
    op.drop_index("ix_attempt_responses_attempt", table_name="practice_attempt_responses")
    op.drop_table("practice_attempt_responses")
    op.drop_index("ix_practice_attempts_owner_status", table_name="practice_attempts")
    op.drop_table("practice_attempts")
    op.drop_table("practice_exam_questions")
    op.drop_index("ix_practice_exams_owner_subject", table_name="practice_exams")
    op.drop_table("practice_exams")
