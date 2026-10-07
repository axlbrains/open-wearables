"""merge heads

Revision ID: 4bd509f6e264
Revises: 93913ceaac81, 4b9d28928ca1

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "4bd509f6e264"
down_revision: Union[str, None] = ("93913ceaac81", "4b9d28928ca1")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
