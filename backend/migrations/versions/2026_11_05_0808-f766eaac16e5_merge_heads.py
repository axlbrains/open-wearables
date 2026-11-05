"""merge heads

Revision ID: f766eaac16e5
Revises: 59e18f7b9937, 3f6b9c2d8e41

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "f766eaac16e5"
down_revision: Union[str, None] = ("59e18f7b9937", "3f6b9c2d8e41")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
