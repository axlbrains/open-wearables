"""merge heads

Revision ID: 93913ceaac81
Revises: 14456a141c7b, a18e054b6e0f

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "93913ceaac81"
down_revision: Union[str, None] = ("14456a141c7b", "a18e054b6e0f")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
