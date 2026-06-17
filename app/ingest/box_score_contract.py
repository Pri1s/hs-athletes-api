from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable


STAT_FIELDS = (
    "points",
    "rebounds",
    "assists",
    "steals",
    "blocks",
    "minutes_played",
    "free_throws_made",
    "free_throws_attempted",
    "turnovers",
    "fouls",
)


@dataclass(frozen=True)
class BoxScoreGame:
    source_system: str
    source_url: str
    game_date: date
    team_name: str
    opponent_name: str
    external_game_id: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.source_system, "source_system")
        _require_text(self.source_url, "source_url")
        _require_text(self.team_name, "team_name")
        _require_text(self.opponent_name, "opponent_name")
        if not isinstance(self.game_date, date):
            raise TypeError("game_date must be a date")
        _validate_optional_text(self.external_game_id, "external_game_id")


@dataclass(frozen=True)
class BoxScorePlayerStats:
    game: BoxScoreGame
    player_name: str
    external_profile_id: str | None = None
    profile_url: str | None = None
    points: int | None = None
    rebounds: int | None = None
    assists: int | None = None
    steals: int | None = None
    blocks: int | None = None
    minutes_played: int | None = None
    free_throws_made: int | None = None
    free_throws_attempted: int | None = None
    turnovers: int | None = None
    fouls: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.game, BoxScoreGame):
            raise TypeError("game must be a BoxScoreGame")
        _require_text(self.player_name, "player_name")
        _validate_optional_text(self.external_profile_id, "external_profile_id")
        _validate_optional_text(self.profile_url, "profile_url")
        if self.external_profile_id is None and self.profile_url is None:
            raise ValueError("external_profile_id or profile_url is required")
        for field_name in STAT_FIELDS:
            _validate_optional_non_negative_int(getattr(self, field_name), field_name)


def validate_box_score_rows(rows: Iterable[BoxScorePlayerStats]) -> list[BoxScorePlayerStats]:
    validated_rows = list(rows)
    if not validated_rows:
        raise ValueError("at least one box score row is required")
    for row in validated_rows:
        if not isinstance(row, BoxScorePlayerStats):
            raise TypeError("all rows must be BoxScorePlayerStats")
    return validated_rows


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} is required")


def _validate_optional_text(value: str | None, field_name: str) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip()):
        raise ValueError(f"{field_name} must be non-empty when provided")


def _validate_optional_non_negative_int(value: int | None, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an int or None")
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")
