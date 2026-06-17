"""initial schema

Revision ID: 1c50463b1679
Revises:
Create Date: 2026-06-12 17:34:21.836808

Lean team-centered data foundation. Elite circuits, academy teams, and
traditional programs are all modeled as teams so roster and box-score
ingestion can bind directly to source-provided team and player identifiers.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1c50463b1679'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(r"""
create table teams (
    id              bigint generated always as identity primary key,
    name            text not null,
    governing_body  text not null,
    state_code      varchar(2)
);

create table players (
    id                  bigint generated always as identity primary key,
    full_name           text not null,
    expected_grad_year  integer,
    external_source_id  text unique
);

create table rosters (
    id             bigint generated always as identity primary key,
    player_id      bigint not null references players (id),
    team_id        bigint not null references teams (id),
    season_label   text not null,
    jersey_number  smallint,
    position       text
);

create table games (
    id                bigint generated always as identity primary key,
    game_date         date not null,
    home_team_id      bigint not null references teams (id),
    away_team_id      bigint not null references teams (id),
    timing_structure  text
);

create table game_stats (
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
);
""")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
drop table game_stats;
drop table games;
drop table rosters;
drop table players;
drop table teams;
""")
