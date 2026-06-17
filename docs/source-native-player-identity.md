# Source-Native Player Identity

Sprint 1 player identity is scoped to the official source system. The internal
`players.id` remains the stable database/API key, while scraper and loader code
should resolve source rows by `(source_system, external_source_id)`.

## Source Systems

- `eybl_scholastic`: use the EYBL Scholastic roster profile `rp_id` value as
  `external_source_id`.
- `overtime_elite`: use the Overtime Elite player profile UUID as
  `external_source_id`.

`source_profile_url` stores the official profile URL used to identify the
player. Descriptive fields such as name, team, jersey, position, and graduation
year are not identity keys for Sprint 1.
