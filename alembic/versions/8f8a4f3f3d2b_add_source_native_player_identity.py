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
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = "8f8a4f3f3d2b"
down_revision: Union[str, Sequence[str], None] = "cf1c477504c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "rosters" in tables:
        roster_columns = {column["name"] for column in inspector.get_columns("rosters")}
        if "player_id" not in roster_columns and "legacy_rosters" not in tables:
            op.rename_table("rosters", "legacy_rosters")
            tables.remove("rosters")
            tables.add("legacy_rosters")

    if "games" in tables:
        game_columns = {column["name"] for column in inspector.get_columns("games")}
        if "home_team_id" not in game_columns and "legacy_games" not in tables:
            op.rename_table("games", "legacy_games")
            tables.remove("games")
            tables.add("legacy_games")

    if "game_stats" in tables:
        stat_columns = {column["name"] for column in inspector.get_columns("game_stats")}
        if "player_id" not in stat_columns and "legacy_game_stats" not in tables:
            op.rename_table("game_stats", "legacy_game_stats")
            tables.remove("game_stats")
            tables.add("legacy_game_stats")

    op.execute(
        """
        create table if not exists teams (
            id              bigint generated always as identity primary key,
            name            text not null,
            governing_body  text not null,
            state_code      varchar(2)
        )
        """
    )
    op.execute(
        """
        create table if not exists players (
            id                  bigint generated always as identity primary key,
            full_name           text not null,
            expected_grad_year  integer,
            external_source_id  text,
            source_system       text not null default 'legacy',
            source_profile_url  text
        )
        """
    )
    op.execute(
        """
        create table if not exists rosters (
            id             bigint generated always as identity primary key,
            player_id      bigint not null references players (id),
            team_id        bigint not null references teams (id),
            season_label   text not null,
            jersey_number  smallint,
            position       text
        )
        """
    )
    op.execute(
        """
        create table if not exists games (
            id                bigint generated always as identity primary key,
            game_date         date not null,
            home_team_id      bigint not null references teams (id),
            away_team_id      bigint not null references teams (id),
            timing_structure  text
        )
        """
    )
    op.execute(
        """
        create table if not exists game_stats (
            id          bigint generated always as identity primary key,
            player_id   bigint not null references players (id),
            game_id     bigint not null references games (id),
            team_id     bigint not null references teams (id),
            source_url  text not null,
            points      integer,
            rebounds    integer,
            assists     integer,
            steals      integer,
            blocks      integer,
            turnovers   integer,
            ft_made     integer,
            ft_att      integer,
            fouls       integer,
            min_played  integer
        )
        """
    )

    player_columns = {column["name"] for column in inspect(bind).get_columns("players")}
    if "source_system" not in player_columns:
        op.add_column("players", sa.Column("source_system", sa.Text(), nullable=True))
    if "source_profile_url" not in player_columns:
        op.add_column("players", sa.Column("source_profile_url", sa.Text(), nullable=True))

    op.execute("update players set source_system = 'legacy' where source_system is null")
    op.alter_column("players", "source_system", nullable=False)

    op.execute("alter table players drop constraint if exists players_external_source_id_key")
    op.execute(
        """
        do $$
        begin
            if not exists (
                select 1
                from pg_constraint
                where conname = 'uq_players_source_system_external_source_id'
            ) then
                alter table players
                add constraint uq_players_source_system_external_source_id
                unique (source_system, external_source_id);
            end if;
        end
        $$;
        """
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
