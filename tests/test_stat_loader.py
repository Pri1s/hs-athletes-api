from datetime import date
import unittest

from app.ingest.box_score_contract import BoxScoreGame, BoxScorePlayerStats
from app.ingest.stat_loader import load_box_score_rows, mark_etl_exception


class FakeResult:
    def __init__(self, value=None):
        self.value = value

    def scalar_one(self):
        return self.value

    def scalar_one_or_none(self):
        return self.value


class FakeConnection:
    def __init__(self, players=None):
        self.players = players or {}
        self.sources = {}
        self.teams = {}
        self.games = {}
        self.game_stats = {}
        self.exceptions = {}
        self.exception_statuses = {}
        self.player_lookups = []
        self.next_source_id = 1
        self.next_team_id = 10
        self.next_game_id = 100
        self.next_exception_id = 1000

    def execute(self, statement, params=None):
        params = params or {}
        sql = " ".join(str(statement).split()).lower()

        if sql.startswith("insert into sources"):
            source_id = self.sources.setdefault(params["url"], self.next_source_id)
            if source_id == self.next_source_id:
                self.next_source_id += 1
            return FakeResult(source_id)

        if sql.startswith("insert into teams"):
            key = (params["governing_body"], params["name"])
            team_id = self.teams.setdefault(key, self.next_team_id)
            if team_id == self.next_team_id:
                self.next_team_id += 1
            return FakeResult(team_id)

        if sql.startswith("select id from games"):
            key = (params["game_date"], params["home_team_id"], params["away_team_id"])
            return FakeResult(self.games.get(key))

        if sql.startswith("insert into games"):
            key = (params["game_date"], params["home_team_id"], params["away_team_id"])
            game_id = self.games.setdefault(key, self.next_game_id)
            if game_id == self.next_game_id:
                self.next_game_id += 1
            return FakeResult(game_id)

        if sql.startswith("select id from players"):
            key = (params["source_system"], params["external_source_id"])
            self.player_lookups.append(key)
            return FakeResult(self.players.get(key))

        if sql.startswith("insert into game_stats"):
            key = (params["game_id"], params["player_id"], params["team_id"], params["source_url"])
            self.game_stats[key] = params.copy()
            return FakeResult()

        if sql.startswith("insert into etl_exceptions"):
            key = (
                params["source_url"],
                params["parsing_stage"],
                params["team_name"],
                params["player_name"],
                params["failure_reason"],
            )
            exception = self.exceptions.setdefault(key, params.copy())
            if "id" not in exception:
                exception["id"] = self.next_exception_id
                self.exception_statuses[self.next_exception_id] = "pending"
                self.next_exception_id += 1
            exception.update(params.copy())
            self.exception_statuses[exception["id"]] = "pending"
            return FakeResult()

        if sql.startswith("update etl_exceptions"):
            self.exception_statuses[params["exception_id"]] = params["status"]
            return FakeResult()

        raise AssertionError(f"Unexpected SQL: {statement}")


class StatLoaderTests(unittest.TestCase):
    def test_resolves_players_by_external_id_and_upserts_rich_stats(self) -> None:
        conn = FakeConnection(players={("overtime_elite", "player-1"): 31})
        row = self.row(
            player_name="Name From Box Score",
            external_profile_id="player-1",
            points=12,
            free_throws_made=3,
            free_throws_attempted=4,
            turnovers=2,
            fouls=1,
            minutes_played=28,
        )
        updated_row = self.row(
            player_name="Renamed Player Should Not Matter",
            external_profile_id="player-1",
            points=15,
            free_throws_made=4,
            free_throws_attempted=5,
            turnovers=1,
            fouls=2,
            minutes_played=29,
        )

        counts = load_box_score_rows(conn, [row])
        updated_counts = load_box_score_rows(conn, [updated_row])

        self.assertEqual(counts["game_stats"], 1)
        self.assertEqual(updated_counts["game_stats"], 1)
        self.assertEqual(len(conn.game_stats), 1)
        stat_row = next(iter(conn.game_stats.values()))
        self.assertEqual(stat_row["player_id"], 31)
        self.assertEqual(stat_row["source_url"], row.game.source_url)
        self.assertEqual(stat_row["points"], 15)
        self.assertEqual(stat_row["ft_made"], 4)
        self.assertEqual(stat_row["ft_att"], 5)
        self.assertEqual(stat_row["turnovers"], 1)
        self.assertEqual(stat_row["fouls"], 2)
        self.assertEqual(stat_row["min_played"], 29)
        self.assertEqual(conn.player_lookups, [("overtime_elite", "player-1"), ("overtime_elite", "player-1")])
        self.assertEqual(conn.exceptions, {})

    def test_queues_rows_missing_external_player_id(self) -> None:
        conn = FakeConnection()
        row = self.row(external_profile_id=None, profile_url="https://overtimeelite.com/players/no-id")

        counts = load_box_score_rows(conn, [row])

        self.assertEqual(counts["exceptions"], 1)
        self.assertEqual(conn.game_stats, {})
        exception = next(iter(conn.exceptions.values()))
        self.assertEqual(exception["failure_reason"], "missing_external_player_id")
        self.assertEqual(exception["profile_url"], "https://overtimeelite.com/players/no-id")
        self.assertEqual(exception["parsing_stage"], "box_score_stat_loader")
        self.assertEqual(conn.exception_statuses[exception["id"]], "pending")

    def test_queues_rows_with_unknown_external_player_id(self) -> None:
        conn = FakeConnection()
        row = self.row(external_profile_id="unknown-player")

        counts = load_box_score_rows(conn, [row])

        self.assertEqual(counts["exceptions"], 1)
        self.assertEqual(conn.game_stats, {})
        self.assertEqual(conn.player_lookups, [("overtime_elite", "unknown-player")])
        exception = next(iter(conn.exceptions.values()))
        self.assertEqual(exception["failure_reason"], "missing_player_source_identity")
        self.assertEqual(exception["external_source_id"], "unknown-player")

    def test_queues_rows_with_unknown_team_context(self) -> None:
        conn = FakeConnection(players={("overtime_elite", "player-1"): 31, ("overtime_elite", "player-2"): 32})
        valid_row = self.row(external_profile_id="player-1")
        unknown_team_row = self.row(
            external_profile_id="player-2",
            team_name="Unknown Team",
            opponent_name="Team Drifty",
        )

        counts = load_box_score_rows(conn, [valid_row, unknown_team_row])

        self.assertEqual(counts["game_stats"], 1)
        self.assertEqual(counts["exceptions"], 1)
        exception = next(iter(conn.exceptions.values()))
        self.assertEqual(exception["failure_reason"], "unknown_team")
        self.assertEqual(exception["team_name"], "Unknown Team")

    def test_queues_raw_rows_missing_required_game_fields(self) -> None:
        conn = FakeConnection()
        raw_row = {
            "source_system": "overtime_elite",
            "source_url": "https://overtimeelite.com/games/missing-date/box_score",
            "team_name": "Team Hardin",
            "player_name": "Example Player",
            "external_profile_id": "player-1",
            "points": 10,
        }

        counts = load_box_score_rows(conn, [raw_row])

        self.assertEqual(counts["exceptions"], 1)
        self.assertEqual(conn.game_stats, {})
        exception = next(iter(conn.exceptions.values()))
        self.assertEqual(exception["failure_reason"], "missing_required_game_field")
        self.assertEqual(exception["source_url"], "https://overtimeelite.com/games/missing-date/box_score")
        self.assertIn('"points": 10', exception["raw_row_data"])

    def test_queues_malformed_raw_stat_rows(self) -> None:
        conn = FakeConnection()

        counts = load_box_score_rows(conn, ["not a stat row"])

        self.assertEqual(counts["exceptions"], 1)
        exception = next(iter(conn.exceptions.values()))
        self.assertEqual(exception["failure_reason"], "malformed_stat_row")
        self.assertEqual(exception["source_system"], "unknown")
        self.assertEqual(exception["source_url"], "unknown")

    def test_marks_exceptions_resolved_or_discarded(self) -> None:
        conn = FakeConnection()
        load_box_score_rows(conn, [self.row(external_profile_id=None)])
        exception = next(iter(conn.exceptions.values()))

        mark_etl_exception(conn, exception["id"], "resolved")
        self.assertEqual(conn.exception_statuses[exception["id"]], "resolved")

        mark_etl_exception(conn, exception["id"], "discarded")
        self.assertEqual(conn.exception_statuses[exception["id"]], "discarded")

        with self.assertRaises(ValueError):
            mark_etl_exception(conn, exception["id"], "ignored")

    def row(
        self,
        player_name: str = "Example Player",
        external_profile_id: str | None = "player-1",
        profile_url: str | None = "https://overtimeelite.com/players/player-1",
        team_name: str = "Team Hardin",
        opponent_name: str = "Team Drifty",
        points: int = 10,
        free_throws_made: int = 1,
        free_throws_attempted: int = 2,
        turnovers: int = 3,
        fouls: int = 4,
        minutes_played: int = 20,
    ) -> BoxScorePlayerStats:
        game = BoxScoreGame(
            source_system="overtime_elite",
            source_url="https://overtimeelite.com/games/game-1/box_score",
            external_game_id="game-1",
            game_date=date(2025, 1, 4),
            team_name=team_name,
            opponent_name=opponent_name,
        )
        return BoxScorePlayerStats(
            game=game,
            player_name=player_name,
            external_profile_id=external_profile_id,
            profile_url=profile_url,
            points=points,
            rebounds=5,
            assists=6,
            steals=1,
            blocks=0,
            minutes_played=minutes_played,
            free_throws_made=free_throws_made,
            free_throws_attempted=free_throws_attempted,
            turnovers=turnovers,
            fouls=fouls,
        )


if __name__ == "__main__":
    unittest.main()
