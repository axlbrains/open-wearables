"""kv_zset_member

Revision ID: 5e1c0a7b2d94
Revises: 4bd509f6e264

Sorted-set storage for the Postgres-backed KvStore (prod has no Redis).
sync_status_service indexes sync runs in sorted sets (ZADD/ZREVRANGE), which
KvStore did not implement: the index writes were skipped and /sync/runs 500'd.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5e1c0a7b2d94"
down_revision: Union[str, None] = "4bd509f6e264"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # One row per member. TTL applies to the whole sorted set (Redis semantics),
    # mirrored on every member like kv_set_member.
    op.create_table(
        "kv_zset_member",
        sa.Column("zset_key", sa.Text, nullable=False),
        sa.Column("member", sa.Text, nullable=False),
        sa.Column("score", sa.Float(precision=53), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("zset_key", "member"),
    )
    op.create_index("ix_kv_zset_member_key_score", "kv_zset_member", ["zset_key", "score"])
    op.create_index(
        "ix_kv_zset_member_expires_at",
        "kv_zset_member",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_kv_zset_member_expires_at", table_name="kv_zset_member")
    op.drop_index("ix_kv_zset_member_key_score", table_name="kv_zset_member")
    op.drop_table("kv_zset_member")
