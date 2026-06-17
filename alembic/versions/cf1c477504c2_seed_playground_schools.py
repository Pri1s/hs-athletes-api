"""retired playground seed

Revision ID: cf1c477504c2
Revises: 1c50463b1679
Create Date: 2026-06-13 00:51:54.806046

Retains the historical revision in the migration chain without seeding data.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cf1c477504c2'
down_revision: Union[str, Sequence[str], None] = '1c50463b1679'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
