"""add roster etl upsert keys

Revision ID: 2bd9cf8186f7
Revises: 8f8a4f3f3d2b
Create Date: 2026-06-17 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "2bd9cf8186f7"
down_revision: Union[str, Sequence[str], None] = "8f8a4f3f3d2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())

    if "sources" not in tables:
        op.create_table(
            "sources",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=True), primary_key=True),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("source_system", sa.Text(), nullable=False),
            sa.Column("fetched_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
            sa.Column("parsing_stage", sa.Text(), nullable=False),
            sa.UniqueConstraint("url", name="uq_sources_url"),
        )
    else:
        source_columns = {column["name"] for column in inspect(bind).get_columns("sources")}
        if "source_system" not in source_columns:
            op.add_column("sources", sa.Column("source_system", sa.Text(), nullable=True))
            op.execute("update sources set source_system = 'legacy' where source_system is null")
            op.alter_column("sources", "source_system", nullable=False)
        if "parsing_stage" not in source_columns:
            op.add_column("sources", sa.Column("parsing_stage", sa.Text(), nullable=True))
            op.execute("update sources set parsing_stage = 'legacy' where parsing_stage is null")
            op.alter_column("sources", "parsing_stage", nullable=False)

    op.execute(
        """
        do $$
        begin
            if not exists (
                select 1
                from pg_constraint
                where conname = 'uq_teams_governing_body_name'
            ) then
                alter table teams
                add constraint uq_teams_governing_body_name
                unique (governing_body, name);
            end if;
        end
        $$;
        """
    )
    op.execute(
        """
        do $$
        begin
            if not exists (
                select 1
                from pg_constraint
                where conname = 'uq_rosters_player_team_season'
            ) then
                alter table rosters
                add constraint uq_rosters_player_team_season
                unique (player_id, team_id, season_label);
            end if;
        end
        $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("uq_rosters_player_team_season", "rosters", type_="unique")
    op.drop_constraint("uq_teams_governing_body_name", "teams", type_="unique")
    op.drop_table("sources")
