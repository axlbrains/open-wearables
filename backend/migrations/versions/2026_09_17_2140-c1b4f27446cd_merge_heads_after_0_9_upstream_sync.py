"""merge heads after 0.9 upstream sync

Revision ID: c1b4f27446cd
Revises: 8bc287ccbf32, a7c3e9f1b2d4

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1b4f27446cd'
down_revision: Union[str, None] = ('8bc287ccbf32', 'a7c3e9f1b2d4')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
