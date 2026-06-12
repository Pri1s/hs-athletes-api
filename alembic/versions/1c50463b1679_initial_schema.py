"""initial schema

Revision ID: 1c50463b1679
Revises:
Create Date: 2026-06-12 17:34:21.836808

Sprint 1 data foundation (S1-004). Scope: UIL public schools, boys
basketball. Partition columns (division, governing_body) are CHECK-locked
to single values rather than omitted, so existing rows stay labeled when
scope expands.
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
create table schools (
    id              bigint generated always as identity primary key,
    name            text not null,
    city            text,
    school_system   text,  -- administrative ISD, e.g. 'Frisco ISD'; NOT the competition district
    governing_body  text not null default 'uil' check (governing_body in ('uil')),
    is_playground   boolean not null default false,  -- S1-005 cohort flag
    created_at      timestamptz not null default now()
);

create table school_seasons (
    id                    bigint generated always as identity primary key,
    school_id             bigint not null references schools (id),
    season_label          text not null check (season_label ~ '^\d{4}-\d{2}$'),  -- e.g. '2025-26'
    classification        text check (classification in ('1A','2A','3A','4A','5A','6A')),  -- UIL enrollment class
    competition_district  smallint,  -- UIL alignment district number; NOT an ISD, NOT the playground cohort
    created_at            timestamptz not null default now(),
    unique (school_id, season_label)
);

create table athletes (
    id                 bigint generated always as identity primary key,
    full_name          text not null,
    expected_grad_year integer not null check (expected_grad_year between 2000 and 2099),
    created_at         timestamptz not null default now()
    -- canonical_player_id (cross-school duplicate linking) deliberately deferred
);

create table rosters (
    id            bigint generated always as identity primary key,
    athlete_id    bigint not null references athletes (id),
    school_id     bigint not null references schools (id),
    season_label  text not null check (season_label ~ '^\d{4}-\d{2}$'),
    division      text not null default 'boys' check (division in ('boys')),
    jersey_number smallint check (jersey_number between 0 and 99),  -- same-name disambiguator; matching signal, not a constraint
    position      text,
    grade_level   smallint check (grade_level between 9 and 12),
    height_inches smallint check (height_inches between 48 and 96),
    created_at    timestamptz not null default now(),
    unique (athlete_id, school_id, season_label, division)
);

create table sources (
    id          bigint generated always as identity primary key,
    url         text not null unique,
    fetched_at  timestamptz not null default now()
);

create table games (
    id              bigint generated always as identity primary key,
    season_label    text not null check (season_label ~ '^\d{4}-\d{2}$'),
    division        text not null default 'boys' check (division in ('boys')),
    game_date       date not null,
    home_school_id  bigint not null references schools (id),
    away_school_id  bigint not null references schools (id),
    game_type       text not null check (game_type in ('district', 'non_district', 'tournament', 'playoff')),
    home_score      integer check (home_score >= 0),  -- nullable until result known
    away_score      integer check (away_score >= 0),
    created_at      timestamptz not null default now(),
    check (home_school_id <> away_school_id),
    unique (game_date, home_school_id, away_school_id, division)
);

create table game_stats (
    id          bigint generated always as identity primary key,
    athlete_id  bigint not null references athletes (id),
    game_id     bigint not null references games (id),
    school_id   bigint not null references schools (id),  -- side the athlete played for
    source_id   bigint not null references sources (id),  -- S1-016 provenance
    points      integer check (points >= 0),  -- stat columns nullable: NULL = source did not report it
    rebounds    integer check (rebounds >= 0),
    assists     integer check (assists >= 0),
    steals      integer check (steals >= 0),
    blocks      integer check (blocks >= 0),
    created_at  timestamptz not null default now(),
    unique (athlete_id, game_id)
);

create table pending_unresolved_stats (
    id                bigint generated always as identity primary key,
    source_id         bigint not null references sources (id),
    source_text       text not null,
    raw_player_name   text not null,
    raw_school_name   text,
    raw_jersey_number smallint,
    raw_grad_year     integer,
    game_id           bigint references games (id),  -- null when the game itself is unresolved
    points            integer check (points >= 0),
    rebounds          integer check (rebounds >= 0),
    assists           integer check (assists >= 0),
    steals            integer check (steals >= 0),
    blocks            integer check (blocks >= 0),
    unresolved_reason text not null,
    status            text not null default 'pending' check (status in ('pending', 'resolved', 'discarded')),
    created_at        timestamptz not null default now()
);
""")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
drop table pending_unresolved_stats;
drop table game_stats;
drop table games;
drop table sources;
drop table rosters;
drop table athletes;
drop table school_seasons;
drop table schools;
""")
