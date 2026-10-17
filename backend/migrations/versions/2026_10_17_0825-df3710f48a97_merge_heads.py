"""merge heads

Revision ID: df3710f48a97
Revises: 0616d4be35c9, c4e7a1d93b52

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "df3710f48a97"
down_revision: Union[str, None] = ("0616d4be35c9", "c4e7a1d93b52")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
