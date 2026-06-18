from __future__ import annotations

import json
from collections import defaultdict
from datetime import date
from typing import Iterable

from sqlalchemy import text

from app.ingest.box_score_contract import BoxScorePlayerStats, validate_box_score_rows


DEFAULT_PARSING_STAGE = "box_score_stat_loader"
EXCEPTION_STATUSES = {"pending", "resolved", "discarded"}
REQUIRED_GAME_FIELDS = ("source_system", "source_url", "game_date", "team_name", "opponent_name")
SOURCE_GOVERNING_BODIES = {
    "eybl_scholastic": "EYBL Scholastic",
    "overtime_elite": "OTE",
}


def load_box_score_rows(conn, rows: Iterable[object]) -> dict[str, int]:
    raw_rows = list(rows)
    if not raw_rows:
        raise ValueError("at least one box score row is required")

    validated_rows: list[BoxScorePlayerStats] = []
    queued_exceptions = 0

    for raw_row in raw_rows:
        if isinstance(raw_row, BoxScorePlayerStats):
            validated_rows.append(raw_row)
            continue
        _queue_raw_exception(conn, raw_row, _raw_failure_reason(raw_row))
        queued_exceptions += 1

    if validated_rows:
        validated_rows = validate_box_score_rows(validated_rows)

    grouped_rows = _group_rows_by_game(validated_rows)
    team_ids: dict[tuple[str, str], int] = {}
    seen_sources: set[str] = set()
    seen_teams: set[tuple[str, str]] = set()
    seen_games: set[int] = set()
    resolved_players: set[int] = set()
    upserted_stats = 0

    for game_rows in grouped_rows.values():
        game = game_rows[0].game
        _upsert_source(conn, game.source_url, game.source_system)
        seen_sources.add(game.source_url)

        away_team_name, home_team_name = _game_team_names(game_rows)
        expected_team_names = {away_team_name, home_team_name}
        governing_body = _governing_body(game.source_system)
        away_team_id = _upsert_team(conn, team_ids, governing_body, away_team_name)
        home_team_id = _upsert_team(conn, team_ids, governing_body, home_team_name)
        seen_teams.add((governing_body, away_team_name))
        seen_teams.add((governing_body, home_team_name))

        game_id = _upsert_game(conn, game.game_date, home_team_id, away_team_id)
        seen_games.add(game_id)

        for row in game_rows:
            if {row.game.team_name, row.game.opponent_name} != expected_team_names:
                _queue_row_exception(conn, row, "unknown_team")
                queued_exceptions += 1
                continue

            if row.external_profile_id is None:
                _queue_row_exception(conn, row, "missing_external_player_id")
                queued_exceptions += 1
                continue

            player_id = _resolve_player_id(conn, row.game.source_system, row.external_profile_id)
            if player_id is None:
                _queue_row_exception(conn, row, "missing_player_source_identity")
                queued_exceptions += 1
                continue

            team_id = _upsert_team(conn, team_ids, governing_body, row.game.team_name)
            seen_teams.add((governing_body, row.game.team_name))
            _upsert_game_stat(conn, row, game_id, player_id, team_id)
            resolved_players.add(player_id)
            upserted_stats += 1

    return {
        "sources": len(seen_sources),
        "teams": len(seen_teams),
        "games": len(seen_games),
        "players": len(resolved_players),
        "game_stats": upserted_stats,
        "exceptions": queued_exceptions,
    }


def mark_etl_exception(conn, exception_id: int, status: str) -> None:
    if status not in EXCEPTION_STATUSES:
        raise ValueError("status must be pending, resolved, or discarded")

    conn.execute(
        text(
            """
            update etl_exceptions
            set status = :status,
                updated_at = now()
            where id = :exception_id
            """
        ),
        {"exception_id": exception_id, "status": status},
    )


def _group_rows_by_game(rows: Iterable[BoxScorePlayerStats]) -> dict[tuple[str, str], list[BoxScorePlayerStats]]:
    grouped_rows: dict[tuple[str, str], list[BoxScorePlayerStats]] = defaultdict(list)
    for row in rows:
        key = (row.game.source_system, row.game.source_url)
        grouped_rows[key].append(row)
    return grouped_rows


def _governing_body(source_system: str) -> str:
    return SOURCE_GOVERNING_BODIES.get(source_system, source_system)


def _game_team_names(rows: list[BoxScorePlayerStats]) -> tuple[str, str]:
    names: list[str] = []
    for row in rows:
        for name in (row.game.team_name, row.game.opponent_name):
            if name not in names:
                names.append(name)
    if len(names) < 2:
        raise ValueError("box score rows must identify both teams in the game")
    return names[0], names[1]


def _upsert_source(conn, source_url: str, source_system: str) -> int:
    return conn.execute(
        text(
            """
            insert into sources (url, source_system, fetched_at, parsing_stage)
            values (:url, :source_system, now(), :parsing_stage)
            on conflict (url) do update
            set fetched_at = excluded.fetched_at,
                source_system = excluded.source_system,
                parsing_stage = excluded.parsing_stage
            returning id
            """
        ),
        {
            "url": source_url,
            "source_system": source_system,
            "parsing_stage": "box_score_stat_loader",
        },
    ).scalar_one()


def _upsert_team(conn, team_ids: dict[tuple[str, str], int], governing_body: str, team_name: str) -> int:
    team_key = (governing_body, team_name)
    if team_key not in team_ids:
        team_ids[team_key] = conn.execute(
            text(
                """
                insert into teams (name, governing_body, state_code)
                values (:name, :governing_body, null)
                on conflict (governing_body, name) do update
                set name = excluded.name
                returning id
                """
            ),
            {"name": team_name, "governing_body": governing_body},
        ).scalar_one()
    return team_ids[team_key]


def _upsert_game(conn, game_date, home_team_id: int, away_team_id: int) -> int:
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
            "game_date": game_date,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
        },
    ).scalar_one_or_none()

    if game_id is not None:
        return game_id

    return conn.execute(
        text(
            """
            insert into games (game_date, home_team_id, away_team_id, timing_structure)
            values (:game_date, :home_team_id, :away_team_id, :timing_structure)
            returning id
            """
        ),
        {
            "game_date": game_date,
            "home_team_id": home_team_id,
            "away_team_id": away_team_id,
            "timing_structure": None,
        },
    ).scalar_one()


def _resolve_player_id(conn, source_system: str, external_source_id: str) -> int | None:
    return conn.execute(
        text(
            """
            select id
            from players
            where source_system = :source_system
              and external_source_id = :external_source_id
            """
        ),
        {
            "source_system": source_system,
            "external_source_id": external_source_id,
        },
    ).scalar_one_or_none()


def _upsert_game_stat(conn, row: BoxScorePlayerStats, game_id: int, player_id: int, team_id: int) -> None:
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
            on conflict (game_id, player_id, team_id, source_url) do update
            set points = excluded.points,
                rebounds = excluded.rebounds,
                assists = excluded.assists,
                steals = excluded.steals,
                blocks = excluded.blocks,
                turnovers = excluded.turnovers,
                ft_made = excluded.ft_made,
                ft_att = excluded.ft_att,
                fouls = excluded.fouls,
                min_played = excluded.min_played
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


def _queue_row_exception(conn, row: BoxScorePlayerStats, failure_reason: str) -> None:
    _queue_etl_exception(
        conn,
        source_system=row.game.source_system,
        source_url=row.game.source_url,
        external_game_id=row.game.external_game_id,
        game_date=row.game.game_date,
        team_name=row.game.team_name,
        opponent_name=row.game.opponent_name,
        player_name=row.player_name,
        external_source_id=row.external_profile_id,
        profile_url=row.profile_url,
        parsing_stage=DEFAULT_PARSING_STAGE,
        failure_reason=failure_reason,
        raw_row_data=_row_payload(row),
    )


def _queue_raw_exception(conn, raw_row: object, failure_reason: str) -> None:
    payload = _raw_row_payload(raw_row)
    game = payload.get("game") if isinstance(payload.get("game"), dict) else {}
    source_system = _string_value(game.get("source_system") or payload.get("source_system")) or "unknown"
    source_url = _string_value(game.get("source_url") or payload.get("source_url")) or "unknown"

    _queue_etl_exception(
        conn,
        source_system=source_system,
        source_url=source_url,
        external_game_id=_string_value(game.get("external_game_id") or payload.get("external_game_id")),
        game_date=_date_value(game.get("game_date") or payload.get("game_date")),
        team_name=_string_value(game.get("team_name") or payload.get("team_name")),
        opponent_name=_string_value(game.get("opponent_name") or payload.get("opponent_name")),
        player_name=_string_value(payload.get("player_name")),
        external_source_id=_string_value(payload.get("external_profile_id") or payload.get("external_source_id")),
        profile_url=_string_value(payload.get("profile_url")),
        parsing_stage=_string_value(payload.get("parsing_stage")) or DEFAULT_PARSING_STAGE,
        failure_reason=failure_reason,
        raw_row_data=payload,
    )


def _queue_etl_exception(
    conn,
    *,
    source_system: str,
    source_url: str,
    external_game_id: str | None,
    game_date: date | None,
    team_name: str | None,
    opponent_name: str | None,
    player_name: str | None,
    external_source_id: str | None,
    profile_url: str | None,
    parsing_stage: str,
    failure_reason: str,
    raw_row_data: dict[str, object],
) -> None:
    conn.execute(
        text(
            """
            insert into etl_exceptions (
                source_system,
                source_url,
                external_game_id,
                game_date,
                team_name,
                opponent_name,
                player_name,
                external_source_id,
                profile_url,
                parsing_stage,
                failure_reason,
                raw_row_data
            )
            values (
                :source_system,
                :source_url,
                :external_game_id,
                :game_date,
                :team_name,
                :opponent_name,
                :player_name,
                :external_source_id,
                :profile_url,
                :parsing_stage,
                :failure_reason,
                cast(:raw_row_data as jsonb)
            )
            on conflict (source_url, parsing_stage, team_name, player_name, failure_reason) do update
            set external_source_id = excluded.external_source_id,
                profile_url = excluded.profile_url,
                raw_row_data = excluded.raw_row_data,
                status = 'pending',
                updated_at = now()
            """
        ),
        {
            "source_system": source_system,
            "source_url": source_url,
            "external_game_id": external_game_id,
            "game_date": game_date,
            "team_name": team_name,
            "opponent_name": opponent_name,
            "player_name": player_name,
            "external_source_id": external_source_id,
            "profile_url": profile_url,
            "parsing_stage": parsing_stage,
            "failure_reason": failure_reason,
            "raw_row_data": json.dumps(raw_row_data, default=str, sort_keys=True),
        },
    )


def _row_payload(row: BoxScorePlayerStats) -> dict[str, object]:
    return {
        "game": {
            "source_system": row.game.source_system,
            "source_url": row.game.source_url,
            "external_game_id": row.game.external_game_id,
            "game_date": row.game.game_date.isoformat(),
            "team_name": row.game.team_name,
            "opponent_name": row.game.opponent_name,
        },
        "player_name": row.player_name,
        "external_profile_id": row.external_profile_id,
        "profile_url": row.profile_url,
        "points": row.points,
        "rebounds": row.rebounds,
        "assists": row.assists,
        "steals": row.steals,
        "blocks": row.blocks,
        "minutes_played": row.minutes_played,
        "free_throws_made": row.free_throws_made,
        "free_throws_attempted": row.free_throws_attempted,
        "turnovers": row.turnovers,
        "fouls": row.fouls,
    }


def _raw_failure_reason(raw_row: object) -> str:
    if not isinstance(raw_row, dict):
        return "malformed_stat_row"

    payload = _raw_row_payload(raw_row)
    game = payload.get("game") if isinstance(payload.get("game"), dict) else payload
    if any(not _string_value(game.get(field_name)) for field_name in REQUIRED_GAME_FIELDS if field_name != "game_date"):
        return "missing_required_game_field"
    if _date_value(game.get("game_date")) is None:
        return "missing_required_game_field"
    return "malformed_stat_row"


def _raw_row_payload(raw_row: object) -> dict[str, object]:
    if isinstance(raw_row, dict):
        return raw_row
    return {"raw": repr(raw_row)}


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _date_value(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None
