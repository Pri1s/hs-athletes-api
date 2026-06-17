import unittest

from app.ingest.benchmark_game import (
    BENCHMARK_AWAY_TEAM,
    BENCHMARK_EXTERNAL_GAME_ID,
    BENCHMARK_GAME_DATE,
    BENCHMARK_HOME_TEAM,
    BENCHMARK_SOURCE_SYSTEM,
    BENCHMARK_SOURCE_URL,
    BENCHMARK_TEAMS,
    benchmark_game_rows,
    benchmark_payload,
    benchmark_roster_rows,
)
from app.ingest.box_score_contract import validate_box_score_rows


class BenchmarkGameTests(unittest.TestCase):
    def test_fixture_uses_official_ote_benchmark_source(self) -> None:
        payload = benchmark_payload()

        self.assertEqual(payload["source_system"], "overtime_elite")
        self.assertEqual(payload["source_url"], "https://overtimeelite.com/games/8b68a04d-3a58-4032-a4d3-5277eeef2ead/box_score")
        self.assertEqual(payload["external_game_id"], "8b68a04d-3a58-4032-a4d3-5277eeef2ead")
        self.assertEqual(payload["game_date"], "2025-01-04")
        self.assertEqual(payload["home_team"], "Team Drifty")
        self.assertEqual(payload["away_team"], "Team Hardin")
        self.assertEqual(payload["home_score"], 87)
        self.assertEqual(payload["away_score"], 82)

    def test_fixture_has_participating_teams_and_source_native_players(self) -> None:
        team_names = {team.team_name for team in BENCHMARK_TEAMS}
        roster_rows = benchmark_roster_rows()

        self.assertEqual(team_names, {BENCHMARK_AWAY_TEAM, BENCHMARK_HOME_TEAM})
        self.assertEqual({row.team_name for row in roster_rows}, team_names)
        self.assertTrue(all(row.source_system == BENCHMARK_SOURCE_SYSTEM for row in roster_rows))
        self.assertTrue(all(row.external_profile_id for row in roster_rows))
        self.assertTrue(all(row.profile_url.startswith("https://overtimeelite.com/players/") for row in roster_rows))

    def test_box_score_rows_match_contract_and_cover_both_teams(self) -> None:
        rows = benchmark_game_rows()

        self.assertEqual(validate_box_score_rows(rows), rows)
        self.assertEqual({row.game.team_name for row in rows}, {BENCHMARK_AWAY_TEAM, BENCHMARK_HOME_TEAM})
        self.assertTrue(all(row.game.source_url == BENCHMARK_SOURCE_URL for row in rows))
        self.assertTrue(all(row.game.external_game_id == BENCHMARK_EXTERNAL_GAME_ID for row in rows))
        self.assertTrue(all(row.game.game_date == BENCHMARK_GAME_DATE for row in rows))
        self.assertTrue(all(row.external_profile_id or row.profile_url for row in rows))


if __name__ == "__main__":
    unittest.main()
