import unittest

from app.ingest.circuit_rosters import RosterRow, parse_eybl_box_score


BOX_SCORE_HTML = """
<html>
  <body>
    <dl>
      <dt>Date</dt>
      <dd>11/28/2025</dd>
    </dl>
    <table>
      <caption>Team Score By Half</caption>
      <tr><th>Team</th><th>1</th><th>Total F</th></tr>
      <tr><td>Iowa United</td><td>67</td><td>67</td></tr>
      <tr><td>Spire</td><td>75</td><td>75</td></tr>
    </table>
    <table>
      <caption>Iowa United - Team Statistics</caption>
      <tr>
        <th>##</th><th>Player</th><th>GS</th><th>MIN</th><th>FT</th>
        <th>REB</th><th>PF</th><th>A</th><th>TO</th><th>BLK</th><th>STL</th><th>PTS</th>
      </tr>
      <tr>
        <td>3</td>
        <th scope="row"><span class="mobile-jersey-number">3</span> Sigmon,Jordan</th>
        <td>*</td>
        <td data-label="MIN">30+</td>
        <td data-label="FT">0-0</td>
        <td data-label="REB">4</td>
        <td data-label="PF">3</td>
        <td data-label="A">4</td>
        <td data-label="TO">2</td>
        <td data-label="BLK">0</td>
        <td data-label="STL">0</td>
        <td data-label="PTS">21</td>
      </tr>
      <tr>
        <td></td><th scope="row">Totals</th><td data-label="PTS">67</td>
      </tr>
    </table>
    <table>
      <caption>Spire - Team Statistics</caption>
      <tr>
        <th>##</th><th>Player</th><th>GS</th><th>MIN</th><th>FT</th>
        <th>REB</th><th>PF</th><th>A</th><th>TO</th><th>BLK</th><th>STL</th><th>PTS</th>
      </tr>
      <tr>
        <td>4</td>
        <th scope="row"><span class="mobile-jersey-number">4</span> Derkack,Aiden</th>
        <td>*</td>
        <td data-label="MIN"></td>
        <td data-label="FT">3-6</td>
        <td data-label="REB">3</td>
        <td data-label="PF">3</td>
        <td data-label="A">2</td>
        <td data-label="TO">1</td>
        <td data-label="BLK">0</td>
        <td data-label="STL">2</td>
        <td data-label="PTS">17</td>
      </tr>
    </table>
  </body>
</html>
"""


class EyblBoxScoreScraperTests(unittest.TestCase):
    def test_parses_eybl_box_score_rows_with_roster_identity(self) -> None:
        roster_rows = [
            self.roster_row(
                team_name="Iowa United",
                team_slug="Iowa",
                player_name="Jordan Sigmon",
                external_profile_id="604",
            ),
            self.roster_row(
                team_name="Spire Institute Academy",
                team_slug="Spire",
                player_name="Aiden Derkack",
                external_profile_id="681",
            ),
        ]

        rows = parse_eybl_box_score(
            BOX_SCORE_HTML,
            "https://nikeeyblscholastic.com/boxscore.aspx?id=game-token&path=mbball",
            roster_rows,
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].game.source_system, "eybl_scholastic")
        self.assertEqual(rows[0].game.external_game_id, "game-token")
        self.assertEqual(rows[0].game.team_name, "Iowa United")
        self.assertEqual(rows[0].game.opponent_name, "Spire")
        self.assertEqual(rows[0].player_name, "Jordan Sigmon")
        self.assertEqual(rows[0].external_profile_id, "604")
        self.assertEqual(rows[0].points, 21)
        self.assertEqual(rows[0].minutes_played, 30)
        self.assertEqual(rows[0].free_throws_made, 0)
        self.assertEqual(rows[0].free_throws_attempted, 0)
        self.assertEqual(rows[0].blocks, 0)
        self.assertIsNone(rows[1].minutes_played)
        self.assertEqual(rows[1].free_throws_made, 3)
        self.assertEqual(rows[1].free_throws_attempted, 6)

    def test_logs_source_url_and_stage_when_identity_is_missing(self) -> None:
        source_url = "https://nikeeyblscholastic.com/boxscore.aspx?id=game-token&path=mbball"

        with self.assertLogs("hs_athletes", level="ERROR") as captured:
            with self.assertRaises(ValueError):
                parse_eybl_box_score(BOX_SCORE_HTML, source_url, [])

        self.assertIn(f"source_url={source_url}", captured.output[0])
        self.assertIn("parsing_stage=box_score_identity", captured.output[0])

    def test_can_skip_unresolved_rows_without_emitting_non_contract_rows(self) -> None:
        source_url = "https://nikeeyblscholastic.com/boxscore.aspx?id=game-token&path=mbball"
        roster_rows = [
            self.roster_row(
                team_name="Iowa United",
                team_slug="Iowa",
                player_name="Jordan Sigmon",
                external_profile_id="604",
            )
        ]

        with self.assertLogs("hs_athletes", level="WARNING") as captured:
            rows = parse_eybl_box_score(
                BOX_SCORE_HTML,
                source_url,
                roster_rows,
                skip_unresolved_identities=True,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].player_name, "Jordan Sigmon")
        self.assertEqual(rows[0].external_profile_id, "604")
        self.assertIn(f"source_url={source_url}", captured.output[0])
        self.assertIn("parsing_stage=box_score_identity", captured.output[0])

    def roster_row(
        self,
        team_name: str,
        team_slug: str,
        player_name: str,
        external_profile_id: str,
    ) -> RosterRow:
        return RosterRow(
            source_system="eybl_scholastic",
            governing_body="EYBL Scholastic",
            source_url=f"https://nikeeyblscholastic.com/sports/mbball/{team_slug}/roster/2025-26",
            parsing_stage="eybl_roster",
            team_name=team_name,
            team_slug=team_slug,
            player_name=player_name,
            external_profile_id=external_profile_id,
            profile_url=f"https://nikeeyblscholastic.com/players/{external_profile_id}",
            season_label="2025-26",
            jersey_number=None,
            position=None,
        )


if __name__ == "__main__":
    unittest.main()
