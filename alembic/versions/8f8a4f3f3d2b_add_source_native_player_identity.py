"""add source-native player identity

Revision ID: 8f8a4f3f3d2b
Revises: cf1c477504c2
Create Date: 2026-06-17 09:10:00.000000

Store source-scoped player identifiers so deterministic circuit loaders can
resolve players by official profile IDs instead of name-based matching.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f8a4f3f3d2b"
down_revision: Union[str, Sequence[str], None] = "cf1c477504c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("players", sa.Column("source_system", sa.Text(), nullable=True))
    op.add_column("players", sa.Column("source_profile_url", sa.Text(), nullable=True))

    op.execute("update players set source_system = 'legacy' where source_system is null")
    op.alter_column("players", "source_system", nullable=False)

    op.drop_constraint("players_external_source_id_key", "players", type_="unique")
    op.create_unique_constraint(
        "uq_players_source_system_external_source_id",
        "players",
        ["source_system", "external_source_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_players_source_system_external_source_id",
        "players",
        type_="unique",
    )
    op.create_unique_constraint(
        "players_external_source_id_key",
        "players",
        ["external_source_id"],
    )

    op.drop_column("players", "source_profile_url")
    op.drop_column("players", "source_system")
