"""add external id stat loader keys

Revision ID: 9b4cb8f5a2d1
Revises: 69867f4895b1
Create Date: 2026-06-17 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9b4cb8f5a2d1"
down_revision: Union[str, Sequence[str], None] = "69867f4895b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "pending_unresolved_box_score_rows" not in tables:
        op.create_table(
            "pending_unresolved_box_score_rows",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
            sa.Column("source_system", sa.Text(), nullable=False),
            sa.Column("source_url", sa.Text(), nullable=False),
            sa.Column("external_game_id", sa.Text(), nullable=True),
            sa.Column("game_date", sa.Date(), nullable=False),
            sa.Column("team_name", sa.Text(), nullable=False),
            sa.Column("opponent_name", sa.Text(), nullable=False),
            sa.Column("player_name", sa.Text(), nullable=False),
            sa.Column("external_source_id", sa.Text(), nullable=True),
            sa.Column("profile_url", sa.Text(), nullable=True),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("row_payload", postgresql.JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.UniqueConstraint(
                "source_url",
                "team_name",
                "player_name",
                "reason",
                name="uq_pending_unresolved_box_score_row",
            ),
        )

    constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("game_stats")}
    if "uq_game_stats_game_player_team_source" not in constraints:
        op.execute(
            """
            delete from game_stats older
            using game_stats newer
            where older.id < newer.id
              and older.game_id = newer.game_id
              and older.player_id = newer.player_id
              and older.team_id = newer.team_id
              and older.source_url = newer.source_url
            """
        )
        op.create_unique_constraint(
            "uq_game_stats_game_player_team_source",
            "game_stats",
            ["game_id", "player_id", "team_id", "source_url"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "game_stats" in tables:
        constraints = {constraint["name"] for constraint in inspector.get_unique_constraints("game_stats")}
        if "uq_game_stats_game_player_team_source" in constraints:
            op.drop_constraint("uq_game_stats_game_player_team_source", "game_stats", type_="unique")

    if "pending_unresolved_box_score_rows" in tables:
        op.drop_table("pending_unresolved_box_score_rows")
