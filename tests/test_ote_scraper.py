import unittest

from app.ingest.circuit_rosters import RosterRow, parse_ote_box_score, parse_ote_roster


ROSTER_HTML = """
<html>
  <head><meta property="og:title" content="Blue Checks Roster"></head>
  <body>
    <a class="TeamPlayer" href="/players/af1a0f3f-b0ca-4aeb-a6db-92721fe69070">
      <img alt="Kaylen Chilton">
      <div class="FirstName">Kaylen</div>
      <div class="Number">3</div>
      <div class="LastName">Chilton</div>
      <div class="Position">Guard</div>
    </a>
  </body>
</html>
"""


BOX_SCORE_HTML = """
<html>
  <head>
    <script type="application/ld+json">
      {
        "@context": "https://schema.org",
        "@type": "SportsEvent",
        "startDate": "2025-01-04T00:00:00.000Z"
      }
    </script>
  </head>
  <body>
    <table>
      <tr><th></th><th><span class="desktop-only">Total</span></th></tr>
      <tr><th><span class="desktop-only">Team Hardin</span><span class="mobile-only">HDG</span></th><td>82</td></tr>
      <tr><th><span class="desktop-only">Team Drifty</span><span class="mobile-only">DRI</span></th><td>87</td></tr>
    </table>
    <table>
      <tr>
        <th>Player</th><th>pts</th><th>ast</th><th>orb</th><th>drb</th><th>reb</th>
        <th>stl</th><th>blk</th><th>dnk</th><th>2pm</th><th>2pa</th><th>2p%</th>
        <th>3pm</th><th>3pa</th><th>3p%</th><th>fgm</th><th>fga</th><th>fg%</th>
        <th>ftm</th><th>fta</th><th>ft%</th><th>+/-</th><th>to</th>
      </tr>
      <tr>
        <th><div class="Name">Javon Bardwell</div></th>
        <td>32</td><td>0</td><td>6</td><td>2</td><td>8</td>
        <td>0</td><td>0</td><td>4</td><td>11</td><td>14</td><td>78.6</td>
        <td>3</td><td>9</td><td>33.3</td><td>14</td><td>23</td><td>60.9</td>
        <td>1</td><td>1</td><td>100.0</td><td>6</td><td>2</td>
      </tr>
    </table>
    <table>
      <tr>
        <th>Player</th><th>pts</th><th>ast</th><th>orb</th><th>drb</th><th>reb</th>
        <th>stl</th><th>blk</th><th>dnk</th><th>2pm</th><th>2pa</th><th>2p%</th>
        <th>3pm</th><th>3pa</th><th>3p%</th><th>fgm</th><th>fga</th><th>fg%</th>
        <th>ftm</th><th>fta</th><th>ft%</th><th>+/-</th><th>to</th>
      </tr>
      <tr>
        <th><div class="Name">Team Drifty</div></th>
        <td>87</td><td>17</td><td>42</td><td>59</td><td>101</td>
        <td>9</td><td>0</td><td>25</td><td>62</td><td>73</td><td>84.9</td>
        <td>20</td><td>57</td><td>35.1</td><td>82</td><td>130</td><td>63.1</td>
        <td>3</td><td>4</td><td>75.0</td><td>0</td><td>11</td>
      </tr>
      <tr>
        <th><div class="Name">Josiah Parker</div></th>
        <td>26</td><td>4</td><td>2</td><td>12</td><td>14</td>
        <td>4</td><td>0</td><td>5</td><td>13</td><td>13</td><td>100.0</td>
        <td>0</td><td>1</td><td>0.0</td><td>13</td><td>14</td><td>92.9</td>
        <td>0</td><td>0</td><td>0.0</td><td>10</td><td>4</td>
      </tr>
    </table>
  </body>
</html>
"""


class OteScraperTests(unittest.TestCase):
    def test_parses_ote_roster_player_identity(self) -> None:
        team, rows = parse_ote_roster("blue-checks", ROSTER_HTML, "2025-26")

        self.assertEqual(team.team_name, "Blue Checks")
        self.assertEqual(team.roster_url, "https://overtimeelite.com/teams/blue-checks/roster")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].player_name, "Kaylen Chilton")
        self.assertEqual(rows[0].external_profile_id, "af1a0f3f-b0ca-4aeb-a6db-92721fe69070")
        self.assertEqual(rows[0].profile_url, "https://overtimeelite.com/players/af1a0f3f-b0ca-4aeb-a6db-92721fe69070")
        self.assertEqual(rows[0].jersey_number, 3)
        self.assertEqual(rows[0].position, "Guard")

    def test_parses_ote_box_score_rows_with_source_identity(self) -> None:
        source_url = "https://overtimeelite.com/games/8b68a04d-3a58-4032-a4d3-5277eeef2ead/box_score"
        rows = parse_ote_box_score(
            BOX_SCORE_HTML,
            source_url,
            [
                self.player_identity("Team Hardin", "Javon Bardwell", "db810eaa-6c2f-45f0-94d0-a1a2495894c4"),
                self.player_identity("Team Drifty", "Josiah Parker", "f0bc5d2d-4c59-4230-8726-e860c68f4223"),
            ],
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].game.source_system, "overtime_elite")
        self.assertEqual(rows[0].game.external_game_id, "8b68a04d-3a58-4032-a4d3-5277eeef2ead")
        self.assertEqual(rows[0].game.team_name, "Team Hardin")
        self.assertEqual(rows[0].game.opponent_name, "Team Drifty")
        self.assertEqual(rows[0].game.game_date.isoformat(), "2025-01-04")
        self.assertEqual(rows[0].player_name, "Javon Bardwell")
        self.assertEqual(rows[0].external_profile_id, "db810eaa-6c2f-45f0-94d0-a1a2495894c4")
        self.assertEqual(rows[0].points, 32)
        self.assertEqual(rows[0].rebounds, 8)
        self.assertEqual(rows[0].assists, 0)
        self.assertEqual(rows[0].free_throws_made, 1)
        self.assertEqual(rows[0].free_throws_attempted, 1)
        self.assertEqual(rows[0].turnovers, 2)
        self.assertIsNone(rows[0].minutes_played)
        self.assertIsNone(rows[0].fouls)
        self.assertEqual(rows[1].player_name, "Josiah Parker")
        self.assertEqual(rows[1].free_throws_made, 0)
        self.assertEqual(rows[1].free_throws_attempted, 0)

    def test_logs_when_ote_box_score_identity_is_missing(self) -> None:
        source_url = "https://overtimeelite.com/games/8b68a04d-3a58-4032-a4d3-5277eeef2ead/box_score"

        with self.assertLogs("hs_athletes", level="ERROR") as captured:
            with self.assertRaises(ValueError):
                parse_ote_box_score(BOX_SCORE_HTML, source_url, [])

        self.assertIn(f"source_url={source_url}", captured.output[0])
        self.assertIn("parsing_stage=ote_box_score_identity", captured.output[0])

    def player_identity(self, team_name: str, player_name: str, external_profile_id: str) -> RosterRow:
        return RosterRow(
            source_system="overtime_elite",
            governing_body="OTE",
            source_url=f"https://overtimeelite.com/teams/{team_name.lower().replace(' ', '-')}/roster",
            parsing_stage="ote_roster",
            team_name=team_name,
            team_slug=team_name.lower().replace(" ", "-"),
            player_name=player_name,
            external_profile_id=external_profile_id,
            profile_url=f"https://overtimeelite.com/players/{external_profile_id}",
            season_label="2025-26",
            jersey_number=None,
            position=None,
        )


if __name__ == "__main__":
    unittest.main()
