"""merge heads

Revision ID: 59e18f7b9937
Revises: df3710f48a97, 9ffc050235bd

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "59e18f7b9937"
down_revision: Union[str, None] = ("df3710f48a97", "9ffc050235bd")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
