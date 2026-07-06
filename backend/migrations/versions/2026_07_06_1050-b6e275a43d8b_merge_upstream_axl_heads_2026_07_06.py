"""merge upstream + axl heads 2026_07_06

Revision ID: b6e275a43d8b
Revises: b9cd3eb24460, 9f0940493a9b

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6e275a43d8b'
down_revision: Union[str, None] = ('b9cd3eb24460', '9f0940493a9b')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
