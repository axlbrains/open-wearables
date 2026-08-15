"""merge upstream and axl heads 2026-08-15

Revision ID: 20f158966eb6
Revises: b6e275a43d8b, b2c3d4e5f6a1

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '20f158966eb6'
down_revision: Union[str, None] = ('b6e275a43d8b', 'b2c3d4e5f6a1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
