"""merge heads

Revision ID: 4f05c4e26b6d
Revises: 5e1c0a7b2d94, c4e1a7b93d20

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "4f05c4e26b6d"
down_revision: Union[str, None] = ("5e1c0a7b2d94", "c4e1a7b93d20")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
