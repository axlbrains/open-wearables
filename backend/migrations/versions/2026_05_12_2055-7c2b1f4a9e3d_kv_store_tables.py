"""kv_store_tables

Revision ID: 7c2b1f4a9e3d
Revises: d15dee848b33

Postgres-backed key-value store that replaces Redis for the OW deployment
patterns that don't actually need a separate cache tier (Apple HealthKit
live sleep state, Garmin backfill state, @idempotent locks,
sync_status_service event recording).  See app/integrations/kv_store.py
for the corresponding Redis-compatible API.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7c2b1f4a9e3d"
down_revision: Union[str, None] = "d15dee848b33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Simple key/value with optional TTL.
    op.create_table(
        "kv_entry",
        sa.Column("key", sa.Text, primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_kv_entry_expires_at",
        "kv_entry",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )

    # Set memberships.  TTL applies to the whole set (Redis semantics) — we
    # store the same expires_at on every member of a set and update them
    # together on EXPIRE.
    op.create_table(
        "kv_set_member",
        sa.Column("set_key", sa.Text, nullable=False),
        sa.Column("member", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("set_key", "member"),
    )
    op.create_index(
        "ix_kv_set_member_expires_at",
        "kv_set_member",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )

    # List entries.  ``id`` BIGSERIAL gives us a total ordering — LPUSH
    # inserts a new row, LRANGE 0..N-1 selects ORDER BY id DESC LIMIT N.
    # That matches Redis's "newest first when you LPUSH then LRANGE" model.
    op.create_table(
        "kv_list_entry",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("list_key", sa.Text, nullable=False),
        sa.Column("value", sa.Text, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_kv_list_entry_list_key_id", "kv_list_entry", ["list_key", sa.text("id DESC")])
    op.create_index(
        "ix_kv_list_entry_expires_at",
        "kv_list_entry",
        ["expires_at"],
        postgresql_where=sa.text("expires_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_kv_list_entry_expires_at", table_name="kv_list_entry")
    op.drop_index("ix_kv_list_entry_list_key_id", table_name="kv_list_entry")
    op.drop_table("kv_list_entry")
    op.drop_index("ix_kv_set_member_expires_at", table_name="kv_set_member")
    op.drop_table("kv_set_member")
    op.drop_index("ix_kv_entry_expires_at", table_name="kv_entry")
    op.drop_table("kv_entry")
