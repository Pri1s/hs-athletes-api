"""drop legacy school schema

Revision ID: 51a8f037f327
Revises: 2bd9cf8186f7
Create Date: 2026-06-17 13:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "51a8f037f327"
down_revision: Union[str, Sequence[str], None] = "2bd9cf8186f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    for table_name in (
        "pending_unresolved_stats",
        "school_seasons",
        "legacy_game_stats",
        "legacy_games",
        "legacy_rosters",
        "schools",
        "athletes",
    ):
        if table_name in tables:
            op.drop_table(table_name)


def downgrade() -> None:
    """Downgrade schema."""
    pass
