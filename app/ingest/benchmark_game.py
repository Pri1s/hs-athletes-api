from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import date

from sqlalchemy import text

from app.ingest.box_score_contract import BoxScoreGame, BoxScorePlayerStats, validate_box_score_rows
from app.ingest.circuit_rosters import TeamRecord, RosterRow, upsert_teams


BENCHMARK_SOURCE_SYSTEM = "overtime_elite"
BENCHMARK_GOVERNING_BODY = "OTE"
BENCHMARK_SOURCE_URL = "https://overtimeelite.com/games/8b68a04d-3a58-4032-a4d3-5277eeef2ead/box_score"
BENCHMARK_EXTERNAL_GAME_ID = "8b68a04d-3a58-4032-a4d3-5277eeef2ead"
BENCHMARK_GAME_DATE = date(2025, 1, 4)
BENCHMARK_SEASON_LABEL = "2025-26"
BENCHMARK_HOME_TEAM = "Team Drifty"
BENCHMARK_AWAY_TEAM = "Team Hardin"
BENCHMARK_HOME_SCORE = 87
BENCHMARK_AWAY_SCORE = 82


BENCHMARK_TEAMS = (
    TeamRecord(
        source_system=BENCHMARK_SOURCE_SYSTEM,
        governing_body=BENCHMARK_GOVERNING_BODY,
        team_name=BENCHMARK_AWAY_TEAM,
        team_slug="team-hardin",
        roster_url="https://overtimeelite.com/teams/team-hardin/roster",
    ),
    TeamRecord(
        source_system=BENCHMARK_SOURCE_SYSTEM,
        governing_body=BENCHMARK_GOVERNING_BODY,
        team_name=BENCHMARK_HOME_TEAM,
        team_slug="team-drifty",
        roster_url="https://overtimeelite.com/teams/team-drifty/roster",
    ),
)


def benchmark_roster_rows() -> list[RosterRow]:
    return [
        RosterRow(
            source_system=BENCHMARK_SOURCE_SYSTEM,
            governing_body=BENCHMARK_GOVERNING_BODY,
            source_url="https://overtimeelite.com/teams/team-hardin/roster",
            parsing_stage="benchmark_roster",
            team_name=BENCHMARK_AWAY_TEAM,
            team_slug="team-hardin",
            player_name="Javon Bardwell",
            external_profile_id="db810eaa-6c2f-45f0-94d0-a1a2495894c4",
            profile_url="https://overtimeelite.com/players/db810eaa-6c2f-45f0-94d0-a1a2495894c4",
            season_label=BENCHMARK_SEASON_LABEL,
            jersey_number=None,
            position=None,
        ),
        RosterRow(
            source_system=BENCHMARK_SOURCE_SYSTEM,
            governing_body=BENCHMARK_GOVERNING_BODY,
            source_url="https://overtimeelite.com/teams/team-drifty/roster",
            parsing_stage="benchmark_roster",
            team_name=BENCHMARK_HOME_TEAM,
            team_slug="team-drifty",
            player_name="Josiah Parker",
            external_profile_id="f0bc5d2d-4c59-4230-8726-e860c68f4223",
            profile_url="https://overtimeelite.com/players/f0bc5d2d-4c59-4230-8726-e860c68f4223",
            season_label=BENCHMARK_SEASON_LABEL,
            jersey_number=None,
            position=None,
        ),
    ]


def benchmark_game_rows() -> list[BoxScorePlayerStats]:
    games = {
        BENCHMARK_AWAY_TEAM: BoxScoreGame(
            source_system=BENCHMARK_SOURCE_SYSTEM,
            source_url=BENCHMARK_SOURCE_URL,
            game_date=BENCHMARK_GAME_DATE,
            team_name=BENCHMARK_AWAY_TEAM,
            opponent_name=BENCHMARK_HOME_TEAM,
            external_game_id=BENCHMARK_EXTERNAL_GAME_ID,
        ),
        BENCHMARK_HOME_TEAM: BoxScoreGame(
            source_system=BENCHMARK_SOURCE_SYSTEM,
            source_url=BENCHMARK_SOURCE_URL,
            game_date=BENCHMARK_GAME_DATE,
            team_name=BENCHMARK_HOME_TEAM,
            opponent_name=BENCHMARK_AWAY_TEAM,
            external_game_id=BENCHMARK_EXTERNAL_GAME_ID,
        ),
    }
    return validate_box_score_rows(
        [
            BoxScorePlayerStats(
                game=games[BENCHMARK_AWAY_TEAM],
                player_name="Javon Bardwell",
                external_profile_id="db810eaa-6c2f-45f0-94d0-a1a2495894c4",
                profile_url="https://overtimeelite.com/players/db810eaa-6c2f-45f0-94d0-a1a2495894c4",
                points=32,
                rebounds=8,
                assists=0,
                steals=0,
                blocks=0,
                minutes_played=None,
                free_throws_made=1,
                free_throws_attempted=1,
                turnovers=2,
                fouls=None,
            ),
            BoxScorePlayerStats(
                game=games[BENCHMARK_HOME_TEAM],
                player_name="Josiah Parker",
                external_profile_id="f0bc5d2d-4c59-4230-8726-e860c68f4223",
                profile_url="https://overtimeelite.com/players/f0bc5d2d-4c59-4230-8726-e860c68f4223",
                points=26,
                rebounds=14,
                assists=4,
                steals=4,
                blocks=0,
                minutes_played=None,
                free_throws_made=0,
                free_throws_attempted=0,
                turnovers=4,
                fouls=None,
            ),
        ]
    )


def upsert_benchmark_rosters(conn) -> dict[str, int]:
    team_ids = upsert_teams(conn, BENCHMARK_TEAMS)
    player_ids: dict[str, int] = {}

    for row in benchmark_roster_rows():
        conn.execute(
            text(
                """
                insert into sources (url, source_system, fetched_at, parsing_stage)
                values (:url, :source_system, now(), :parsing_stage)
                on conflict (url) do update
                set fetched_at = excluded.fetched_at,
                    source_system = excluded.source_system,
                    parsing_stage = excluded.parsing_stage
                """
            ),
            {
                "url": row.source_url,
                "source_system": row.source_system,
                "parsing_stage": row.parsing_stage,
            },
        )
        player_id = conn.execute(
            text(
                """
                insert into players (
                    full_name,
                    expected_grad_year,
                    external_source_id,
                    source_system,
                    source_profile_url
                )
                values (
                    :full_name,
                    :expected_grad_year,
                    :external_source_id,
                    :source_system,
                    :source_profile_url
                )
                on conflict (source_system, external_source_id) do update
                set full_name = excluded.full_name,
                    expected_grad_year = excluded.expected_grad_year,
                    source_profile_url = excluded.source_profile_url
                returning id
                """
            ),
            {
                "full_name": row.player_name,
                "expected_grad_year": row.expected_grad_year,
                "external_source_id": row.external_profile_id,
                "source_system": row.source_system,
                "source_profile_url": row.profile_url,
            },
        ).scalar_one()
        player_ids[row.external_profile_id] = player_id

        conn.execute(
            text(
                """
                insert into rosters (
                    player_id,
                    team_id,
                    season_label,
                    jersey_number,
                    position,
                    grade_level,
                    height_inches
                )
                values (
                    :player_id,
                    :team_id,
                    :season_label,
                    :jersey_number,
                    :position,
                    :grade_level,
                    :height_inches
                )
                on conflict (player_id, team_id, season_label) do update
                set jersey_number = excluded.jersey_number,
                    position = excluded.position,
                    grade_level = excluded.grade_level,
                    height_inches = excluded.height_inches
                """
            ),
            {
                "player_id": player_id,
                "team_id": team_ids[(row.governing_body, row.team_name)],
                "season_label": row.season_label,
                "jersey_number": row.jersey_number,
                "position": row.position,
                "grade_level": row.grade_level,
                "height_inches": row.height_inches,
            },
        )

    return player_ids


def seed_benchmark_game(conn) -> dict[str, int]:
    player_ids = upsert_benchmark_rosters(conn)

    conn.execute(
        text(
            """
            insert into sources (url, source_system, fetched_at, parsing_stage)
            values (:url, :source_system, now(), :parsing_stage)
            on conflict (url) do update
            set fetched_at = excluded.fetched_at,
                source_system = excluded.source_system,
                parsing_stage = excluded.parsing_stage
            """
        ),
        {
            "url": BENCHMARK_SOURCE_URL,
            "source_system": BENCHMARK_SOURCE_SYSTEM,
            "parsing_stage": "benchmark_game",
        },
    )

    team_ids = {
        row._mapping["name"]: row._mapping["id"]
        for row in conn.execute(
            text(
                """
                select id, name
                from teams
                where governing_body = :governing_body
                  and name in (:home_team, :away_team)
                """
            ),
            {
                "governing_body": BENCHMARK_GOVERNING_BODY,
                "home_team": BENCHMARK_HOME_TEAM,
                "away_team": BENCHMARK_AWAY_TEAM,
            },
        )
    }
    home_team_id = team_ids[BENCHMARK_HOME_TEAM]
    away_team_id = team_ids[BENCHMARK_AWAY_TEAM]

    game_id = conn.execute(
        text(
            """
            select id
            from games
            where game_date = :game_date
              and home_team_id = :home_team_id
              and away_team_id = :away_team_id
            """
        ),
        {
            "game_date": BENCHMARK_GAME_DATE,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
        },
    ).scalar_one_or_none()

    if game_id is None:
        game_id = conn.execute(
            text(
                """
                insert into games (game_date, home_team_id, away_team_id, timing_structure)
                values (:game_date, :home_team_id, :away_team_id, :timing_structure)
                returning id
                """
            ),
            {
                "game_date": BENCHMARK_GAME_DATE,
                "home_team_id": home_team_id,
                "away_team_id": away_team_id,
                "timing_structure": None,
            },
        ).scalar_one()

    conn.execute(
        text(
            """
            delete from game_stats
            where game_id = :game_id
              and source_url = :source_url
            """
        ),
        {"game_id": game_id, "source_url": BENCHMARK_SOURCE_URL},
    )

    inserted_stats = 0
    for row in benchmark_game_rows():
        team_id = team_ids[row.game.team_name]
        player_id = player_ids[row.external_profile_id]
        conn.execute(
            text(
                """
                insert into game_stats (
                    player_id,
                    game_id,
                    team_id,
                    source_url,
                    points,
                    rebounds,
                    assists,
                    steals,
                    blocks,
                    turnovers,
                    ft_made,
                    ft_att,
                    fouls,
                    min_played
                )
                values (
                    :player_id,
                    :game_id,
                    :team_id,
                    :source_url,
                    :points,
                    :rebounds,
                    :assists,
                    :steals,
                    :blocks,
                    :turnovers,
                    :ft_made,
                    :ft_att,
                    :fouls,
                    :min_played
                )
                """
            ),
            {
                "player_id": player_id,
                "game_id": game_id,
                "team_id": team_id,
                "source_url": row.game.source_url,
                "points": row.points,
                "rebounds": row.rebounds,
                "assists": row.assists,
                "steals": row.steals,
                "blocks": row.blocks,
                "turnovers": row.turnovers,
                "ft_made": row.free_throws_made,
                "ft_att": row.free_throws_attempted,
                "fouls": row.fouls,
                "min_played": row.minutes_played,
            },
        )
        inserted_stats += 1

    return {
        "games": 1,
        "game_stats": inserted_stats,
        "players": len(player_ids),
        "teams": len(team_ids),
    }


def benchmark_payload() -> dict[str, object]:
    return {
        "source_url": BENCHMARK_SOURCE_URL,
        "source_system": BENCHMARK_SOURCE_SYSTEM,
        "external_game_id": BENCHMARK_EXTERNAL_GAME_ID,
        "game_date": BENCHMARK_GAME_DATE.isoformat(),
        "home_team": BENCHMARK_HOME_TEAM,
        "away_team": BENCHMARK_AWAY_TEAM,
        "home_score": BENCHMARK_HOME_SCORE,
        "away_score": BENCHMARK_AWAY_SCORE,
        "teams": [asdict(team) for team in BENCHMARK_TEAMS],
        "rows": [
            {
                "player_name": row.player_name,
                "team_name": row.game.team_name,
                "external_profile_id": row.external_profile_id,
                "profile_url": row.profile_url,
                "points": row.points,
                "rebounds": row.rebounds,
                "assists": row.assists,
                "steals": row.steals,
                "blocks": row.blocks,
                "turnovers": row.turnovers,
                "free_throws_made": row.free_throws_made,
                "free_throws_attempted": row.free_throws_attempted,
                "minutes_played": row.minutes_played,
                "fouls": row.fouls,
            }
            for row in benchmark_game_rows()
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the Sprint 1 benchmark circuit game.")
    parser.add_argument("--load", action="store_true", help="Upsert the benchmark game into the configured database.")
    args = parser.parse_args()

    if not args.load:
        print(json.dumps(benchmark_payload(), indent=2, sort_keys=True))
        return

    from app.db import engine

    with engine.begin() as conn:
        counts = seed_benchmark_game(conn)
    print(json.dumps({"seeded": counts}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
