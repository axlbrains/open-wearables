"""merge heads

Revision ID: 0616d4be35c9
Revises: 4f05c4e26b6d, b679f6226f99

"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "0616d4be35c9"
down_revision: Union[str, None] = ("4f05c4e26b6d", "b679f6226f99")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
