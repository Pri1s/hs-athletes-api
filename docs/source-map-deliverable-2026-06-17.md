# Source Map Deliverable - 2026-06-17

Source: Notion task S1-005, "Research: EYBL and OTE Source Map"

## Objective

Document the deterministic source map for Sprint 1 U18 circuit ingestion.

## Source Priority

- Primary source: official circuit portal pages. Use these first for deterministic ingestion.
- Secondary source: official team/program pages only when the circuit portal is missing a field needed for Sprint 1.
- Aggregators: use only as cross-reference or QA signals. Do not use aggregator rows as primary Sprint 1 source data.

## EYBL Scholastic Source Map

### Official Entry Points

- Circuit homepage: [Nike EYBL Scholastic](https://nikeeyblscholastic.com/)
- Season stats: [2025-2026 Men's Basketball Overall Statistics](https://nikeeyblscholastic.com/stats.aspx?path=mbball&year=2025)
- Team roster pattern: `https://nikeeyblscholastic.com/sports/mbball/{team-slug}/roster/2025-26?path=mbball`
- Example roster/profile page: [Malachi Jordan profile](https://nikeeyblscholastic.com/roster.aspx?rp_id=755)
- Team schedule example: [Spire Institute Academy schedule](https://nikeeyblscholastic.com/schedule.aspx?schedule=87)
- Box score example: [Spire vs Iowa United 11/28/2025](https://nikeeyblscholastic.com/boxscore.aspx?id=JcLFfL9RUu0H5ystoOMbjTxC7HoGm3egED9BeiXiZAnjn2%2FC9ZB%2FpME9lMOEc9V9XvFXg9Ojj9zhtB1283VNrrjF0uAba5evzlUCD2lb5koX1iya6J1LgH8TD28Wa5nFlE9tecX3brS%2Fg4K5%2FEg%2B9vl7euRGkwwXV%2Fj%2BIM%2FckFA%3D&path=mbball)
- Live stats example: `https://live.gamedaypreps.com/{game-id}` appears from some schedule rows; treat as optional secondary source until scraper task verifies shape.

### Stable Identifier Notes

- Player profile URLs expose stable numeric roster-player IDs as `rp_id`, for example `rp_id=755`.
- Raw profile HTML also exposes `rp_id` and `player_id` in embedded page data. Use `rp_id` as the source-native player profile key for Sprint 1.
- Team roster URLs expose team slug and season, but team identity should be normalized from the visible team/program name plus source URL.
- Schedule pages expose numeric `schedule` IDs. Box score URLs expose opaque `id` tokens plus `path=mbball`; store the complete source URL as the source-native game locator.

### Public Fields Available

- Roster/profile fields: player name, jersey number, class/academic year, hometown, height when present, position when present, image URL, bio, historical season fields, source profile URL.
- Schedule fields: date, time, opponent, location/site, result, live stats link, box score link.
- Box score fields: game title, date, site, team score by period, team records when present, player rows with starter marker, minutes, field goals, three-point field goals, free throws, offensive/defensive rebounds, total rebounds, fouls, assists, turnovers, blocks, steals, points, team totals, period splits, team shooting summaries, and game detail fields such as technical fouls, second chance points, points in the paint, fast break points, lead changes, points off turnovers, bench points, and largest lead.
- Stats page fields: team-level season scoring, field goals, three-point field goals, free throws, rebounding, turnovers, miscellaneous categories, leaders, results, and game highs.

### Implementation Flags

- Basic roster, profile, schedule, stats, and box-score data is present in server-rendered HTML. BeautifulSoup/requests should be tried before Playwright.
- Sidearm pages include substantial JavaScript and embedded JSON, but the key Sprint 1 fields are visible in static HTML.
- No authentication observed for the researched pages.
- No pagination observed for the researched static pages; season selectors and schedule IDs must be handled explicitly.
- GamedayPreps live stats are external and may have a different shape. Use only after explicit scraper verification.
- Use normal rate limiting and cache raw HTML snapshots; do not scrape aggressively.

## Overtime Elite Source Map

### Official Entry Points

- Circuit homepage: [OTE](https://overtimeelite.com/)
- Teams index: [OTE teams](https://overtimeelite.com/teams)
- Team page pattern: `https://overtimeelite.com/teams/{team-slug}`
- Team roster example: [Blue Checks roster](https://overtimeelite.com/teams/blue-checks/roster)
- Scores/results: [OTE scores](https://overtimeelite.com/scores)
- Schedule: [OTE schedule](https://overtimeelite.com/schedule)
- Players index: [OTE players](https://overtimeelite.com/players)
- Player profile example: [Isaac Ellis](https://overtimeelite.com/players/e364c331-3868-4366-9df8-c89bd386ca58)
- Stats/leaders: [OTE statistics](https://overtimeelite.com/statistics)
- Box score example: [Team Hardin at Team Drifty box score](https://overtimeelite.com/games/8b68a04d-3a58-4032-a4d3-5277eeef2ead/box_score)

### Stable Identifier Notes

- Player profile URLs expose source-native UUIDs, for example `e364c331-3868-4366-9df8-c89bd386ca58` for Isaac Ellis.
- Game URLs expose source-native UUIDs, for example `8b68a04d-3a58-4032-a4d3-5277eeef2ead`.
- Team URLs expose stable slugs, for example `blue-checks`, `yng-dreamerz`, and `cold-hearts`.
- Player profile HTML also exposes structured metadata and [schema.org](http://schema.org) person data, but the URL UUID should be treated as the source-native player key.

### Public Fields Available

- Team index fields: team names and team slugs.
- Team roster fields: player profile URL, player UUID, first/last name, jersey number when present, position when present, image URL when present.
- Player profile fields: name, team affiliation, position, height, age, weight, graduation year, hometown, profile image, season averages, season totals, game logs, career, biography, [schema.org](http://schema.org) person metadata.
- Scores/schedule fields: date, round/event label, team names, team abbreviations, score, final status, advancement/elimination labels during playoffs, replay links, details links when present.
- Box score fields: game date/event label, teams, abbreviations, score by quarter, final score, replay link, team leaders, team totals, player rows with jersey, name, points, assists, offensive/defensive rebounds, total rebounds, steals, blocks, dunks, two-point makes/attempts/percentage, three-point makes/attempts/percentage, field goals made/attempted/percentage, free throws made/attempted/percentage, plus/minus, fouls when present, turnovers, and play-by-play tab.
- Stats page fields: season leaders for points, assists, rebounds, steals, blocks, and minutes.

### Implementation Flags

- Pages are server-rendered enough for deterministic HTML parsing; no browser rendering is required for the researched fields.
- No authentication observed for researched team, roster, player, scores, stats, schedule, or box-score pages.
- The main schedule page may show no future games when none are scheduled; completed games are available through Scores and team score pages.
- OTE pages use app JavaScript and large inline HTML; scraper should target semantic links, table blocks, and [schema.org](http://schema.org) JSON instead of brittle layout classes where possible.
- No explicit pagination observed in the researched pages, but long players/scores pages may need completeness checks during scraper implementation.
- Use normal rate limiting and cache raw HTML snapshots.

## Scraper Follow-up Targets

- EYBL roster scraper first target: `roster.aspx?rp_id` profile pages plus team roster pages from the main navigation roster list.
- EYBL box-score scraper first target: schedule rows from `schedule.aspx?schedule=87`, then linked `boxscore.aspx` pages.
- OTE roster scraper first target: `/teams/{team-slug}/roster`, extracting `/players/{uuid}` links.
- OTE box-score scraper first target: `/scores` or team score pages, then linked `/games/{uuid}` and `/games/{uuid}/box_score` pages.
- Store raw source URL, source system, source-native player ID, source-native game ID, fetched timestamp, and parsing stage for every extracted row.

## Acceptance Criteria Coverage

- [x] EYBL Scholastic team, roster, player profile, schedule, and box-score entry points are documented.
- [x] Overtime Elite team, roster, player profile, schedule, and box-score entry points are documented.
- [x] Each source notes whether player profile URLs expose stable external IDs.
- [x] Each source notes the public fields available from roster and box-score tables.
- [x] Source priority is documented: official circuit portal first, official team/program page second, aggregator only as cross-reference.
- [x] Sources requiring JavaScript rendering, pagination, authentication, rate limiting care, or manual download are flagged before implementation.
