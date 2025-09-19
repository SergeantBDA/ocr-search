"""merge users and documents heads

Revision ID: cea6507d810f
Revises: 0001_create_users_table, c2404770ca78
Create Date: 2025-09-16 17:41:12.175793

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cea6507d810f'
down_revision: Union[str, Sequence[str], None] = ('0001_create_users_table', 'c2404770ca78')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
