"""merge upstream + axl heads (2026-06-01)

Revision ID: b9cd3eb24460
Revises: 13d979938096, 2d316787b998

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "b9cd3eb24460"
down_revision: Union[str, None] = ("13d979938096", "2d316787b998")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
