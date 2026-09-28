"""merge heads

Revision ID: 14456a141c7b
Revises: ef6ff24def41, c1b4f27446cd

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "14456a141c7b"
down_revision: Union[str, None] = ("ef6ff24def41", "c1b4f27446cd")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
