"""Add shared API authentication rate-limit buckets."""

import sqlalchemy as sa
from alembic import op

revision = "9b2d6f4a1c80"
down_revision = "7a91c4e2d630"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_rate_limit_buckets",
        sa.Column("bucket_key", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.BigInteger(), nullable=False),
        sa.Column("request_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("bucket_key"),
    )
    op.create_index(
        "ix_api_rate_limit_window_start",
        "api_rate_limit_buckets",
        ["window_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_api_rate_limit_window_start", table_name="api_rate_limit_buckets")
    op.drop_table("api_rate_limit_buckets")
