"""merge kv_store and webhook_secret heads

Revision ID: 13d979938096
Revises: 7c2b1f4a9e3d, 6b11080054a0

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '13d979938096'
down_revision: Union[str, None] = ('7c2b1f4a9e3d', '6b11080054a0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
