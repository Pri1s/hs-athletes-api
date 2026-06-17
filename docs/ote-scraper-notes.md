# OTE Scraper Notes

Source: Notion task S1-010, "Implement: Overtime Elite Scraper"

## OTE vs. EYBL Page Shape Differences

- OTE roster pages expose player cards at `/teams/{team-slug}/roster` with `/players/{uuid}` links. The UUID in that URL is the source-native player identifier.
- EYBL roster pages expose roster player IDs in Sidearm roster markup and `roster.aspx?rp_id=...` profile URLs. OTE does not use `rp_id`.
- OTE box-score pages render player stat tables as plain HTML tables with headers such as `pts`, `ast`, `reb`, `stl`, `blk`, `ftm`, `fta`, and `to`. EYBL box scores use Sidearm table captions and `data-label` attributes.
- OTE box-score player rows do not expose profile URLs inline. The scraper resolves source identity from OTE roster/player-index rows by player name before emitting S1-008 contract rows.
- OTE box scores may omit minutes and fouls. The normalized contract keeps those fields as `None`, while visible zeroes in the source table remain integer `0`.
- OTE game IDs are UUIDs in `/games/{uuid}/box_score` URLs. EYBL game IDs are opaque `id` query-string tokens.

## Verification Targets

- Roster source: `https://overtimeelite.com/teams/blue-checks/roster`
- Box-score source: `https://overtimeelite.com/games/8b68a04d-3a58-4032-a4d3-5277eeef2ead/box_score`
