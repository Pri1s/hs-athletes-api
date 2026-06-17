from datetime import date
import unittest

from app.ingest.box_score_contract import (
    BoxScoreGame,
    BoxScorePlayerStats,
    validate_box_score_rows,
)


class BoxScoreContractTests(unittest.TestCase):
    def test_allows_zero_stats_while_preserving_missing_values(self) -> None:
        game = BoxScoreGame(
            source_system="eybl_scholastic",
            source_url="https://nikeeyblscholastic.com/boxscore.aspx?id=game-token",
            external_game_id="game-token",
            game_date=date(2025, 11, 28),
            team_name="Spire",
            opponent_name="Iowa United",
        )

        row = BoxScorePlayerStats(
            game=game,
            player_name="Example Player",
            external_profile_id="755",
            profile_url="https://nikeeyblscholastic.com/sports/mbball/roster/example/755",
            points=0,
            rebounds=None,
            assists=0,
            steals=None,
            blocks=0,
            minutes_played=None,
            free_throws_made=0,
            free_throws_attempted=0,
            turnovers=None,
            fouls=0,
        )

        self.assertEqual(row.points, 0)
        self.assertIsNone(row.rebounds)
        self.assertEqual(validate_box_score_rows([row]), [row])

    def test_requires_player_source_identity(self) -> None:
        game = BoxScoreGame(
            source_system="overtime_elite",
            source_url="https://overtimeelite.com/games/game-id/box_score",
            external_game_id="game-id",
            game_date=date(2025, 11, 28),
            team_name="Team Hardin",
            opponent_name="Team Drifty",
        )

        with self.assertRaises(ValueError):
            BoxScorePlayerStats(game=game, player_name="Example Player", points=12)

    def test_rejects_negative_stats(self) -> None:
        game = BoxScoreGame(
            source_system="overtime_elite",
            source_url="https://overtimeelite.com/games/game-id/box_score",
            game_date=date(2025, 11, 28),
            team_name="Team Hardin",
            opponent_name="Team Drifty",
        )

        with self.assertRaises(ValueError):
            BoxScorePlayerStats(
                game=game,
                player_name="Example Player",
                external_profile_id="player-id",
                points=-1,
            )

    def test_requires_at_least_one_row_before_loading(self) -> None:
        with self.assertRaises(ValueError):
            validate_box_score_rows([])


if __name__ == "__main__":
    unittest.main()
