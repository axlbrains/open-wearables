"""merge upstream and axl heads 2026-09-07

Revision ID: 8bc287ccbf32
Revises: 20f158966eb6, dc5ac28c4b94

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8bc287ccbf32'
down_revision: Union[str, None] = ('20f158966eb6', 'dc5ac28c4b94')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
