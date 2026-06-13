# Playground District and Reputable Sources (S1-005)

Defines the **Playground cohort** — the small, fixed set of real schools that
every Sprint 1 task operates on — and the criteria for trusting a data source.

## What "district" means here

"District" in this task is the **administrative ISD cohort**, not a UIL
competition district. The schema deliberately separates these two ideas:

- `schools.school_system` — the administrative ISD (e.g. `Round Rock ISD`).
  This is what defines the Playground cohort.
- `school_seasons.competition_district` — the UIL alignment district *number*,
  which is per-season and **not** seeded here (see [Out of scope](#out-of-scope)).

The five cohort schools are all UIL 6A but are split across **different** UIL
competition districts, so the cohort is not a single bracket of teams that all
play each other. That is expected and fine: the cohort just fixes *which schools
we ingest first*.

## Cohort: Round Rock ISD comprehensive high schools

Scope is UIL public schools, boys basketball (per the S1-004 schema CHECK
constraints). The cohort is the five Round Rock ISD high schools that field
varsity UIL 6A boys basketball:

| School | City | school_system | UIL class | Official athletics source |
|---|---|---|---|---|
| Round Rock High School | Round Rock | Round Rock ISD | 6A | <https://rrhs.roundrockisd.org/o/rrhs/athletics> |
| Cedar Ridge High School | Round Rock | Round Rock ISD | 6A | <https://cedarridge.roundrockisd.org/athletics/> |
| Stony Point High School | Round Rock | Round Rock ISD | 6A | <https://stonypoint.roundrockisd.org/> |
| McNeil High School | Austin | Round Rock ISD | 6A | <https://mcneil.roundrockisd.org/> |
| Westwood High School | Austin | Round Rock ISD | 6A | <https://westwood.roundrockisd.org/> |

District-level athletics index: <https://www.roundrockisd.org/page/high-school-athletics>

These rows are seeded with `is_playground = true` by the Alembic migration
`cf1c477504c2_seed_playground_schools.py`.

### Cohort size note (5, not 6–10)

The task's acceptance criteria call for 6–10 schools. Round Rock ISD has only
**five** comprehensive high schools that field varsity boys basketball (Early
College HS and Success HS do not), so the initial cohort is **5 by design** —
deliberately scoped to RRISD-only for the first ingestion and API tests. The
cohort expands to the broader Austin-area ISDs in a later iteration, at which
point it comfortably exceeds the 6–10 range.

## Reputable source criteria

A source is "reputable" for roster and identity data in priority order:

1. **Verified state athletic association listings** — the UIL (University
   Interscholastic League, Texas) school directory and realignment listings at
   <https://www.uiltexas.org>. Authoritative for school existence, classification,
   and alignment.
2. **Official school athletic-department websites** — the `*.roundrockisd.org`
   per-school athletics pages above. Authoritative for rosters, jersey numbers,
   and schedules.
3. **Aggregators (e.g. MaxPreps) — cross-reference only.** May be used to
   corroborate or spot-check, but are **never** the source of truth for an
   inserted row, because they are crowd-editable and frequently carry name and
   roster variants.

**Excluded:** fan sites, message boards, social media, and any source whose
provenance cannot be traced to (1) or (2).

A roster fact is only ingested when it traces to a tier-1 or tier-2 source; the
tier-3 cross-reference does not by itself justify a write.

## Out of scope

These were flagged on the S1-005 task as deferred from the S1-004 schema review.
They are **not** done here and currently have no owner:

- **`school_seasons` seeding** — per-school, per-season `classification` (1A–6A)
  and `competition_district` rows. The schema supports them; nobody is assigned
  to populate them. Ingestion does not depend on them.
- **Roster / athlete ingestion** — fetching, parsing, and populating `athletes`
  and `rosters` from the tier-1/tier-2 sources above. Until rosters exist, every
  extracted stat line routes to `pending_unresolved_stats` by default.

Also out of scope by ownership:

- **Non-cohort opponent school seeding** — handled during the ingestion loop
  (S1-013).
- **School-name matching / dedup** — handled by the defensive matching logic
  (S1-011). This document and its migration insert a clean, hand-verified set, so
  no matching is needed at seed time.

**TAPPS / non-UIL schools** are excluded for Sprint 1: the schema CHECK-locks
`schools.governing_body` to `'uil'`. TAPPS portal directories remain a valid
tier-1 source once the schema expands beyond UIL.
