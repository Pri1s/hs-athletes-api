from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, replace
from typing import Iterable
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from sqlalchemy import text

from app.logger import STAGE_DB_MAP, STAGE_DOWNLOAD, STAGE_PARSE, get_logger


OTE_BASE_URL = "https://overtimeelite.com"
EYBL_BASE_URL = "https://nikeeyblscholastic.com"
DEFAULT_SEASON_LABEL = "2025-26"


@dataclass(frozen=True)
class TeamRecord:
    source_system: str
    governing_body: str
    team_name: str
    team_slug: str
    roster_url: str | None = None


@dataclass(frozen=True)
class RosterRow:
    source_system: str
    governing_body: str
    source_url: str
    parsing_stage: str
    team_name: str
    team_slug: str
    player_name: str
    external_profile_id: str
    profile_url: str
    season_label: str
    jersey_number: int | None
    position: str | None
    expected_grad_year: int | None = None
    grade_level: int | None = None
    height_inches: int | None = None


def fetch_html(url: str) -> str:
    logger = get_logger(STAGE_DOWNLOAD)
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "hs-athletes-api-s1-007/1.0"},
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException:
        logger.exception("Failed fetching roster source_url=%s", url)
        raise
    return response.text


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def parse_int(value: str | None) -> int | None:
    cleaned = clean_text(value)
    if cleaned is None or not cleaned.isdigit():
        return None
    return int(cleaned)


def parse_height_inches(value: str | None) -> int | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    match = re.search(r"(\d+)\s*['-]\s*(\d+)", cleaned)
    if not match:
        return None
    return int(match.group(1)) * 12 + int(match.group(2))


def parse_grade_level(value: str | None) -> int | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    normalized = cleaned.lower().strip(".")
    return {
        "fr": 9,
        "freshman": 9,
        "so": 10,
        "sophomore": 10,
        "jr": 11,
        "junior": 11,
        "sr": 12,
        "senior": 12,
    }.get(normalized)


def expected_grad_year_from_grade(season_label: str, grade_level: int | None) -> int | None:
    if grade_level is None:
        return None
    match = re.match(r"(\d{4})", season_label)
    if not match:
        return None
    return int(match.group(1)) + (13 - grade_level)


def ote_roster_url(team_slug: str) -> str:
    return f"{OTE_BASE_URL}/teams/{team_slug}/roster"


def discover_ote_teams() -> list[TeamRecord]:
    html = fetch_html(f"{OTE_BASE_URL}/teams")
    soup = BeautifulSoup(html, "html.parser")
    teams: dict[str, TeamRecord] = {}
    for link in soup.select("a[href^='/teams/']"):
        href = clean_text(link.get("href"))
        if not href:
            continue
        parts = href.strip("/").split("/")
        if len(parts) != 2 or parts[0] != "teams":
            continue
        slug = parts[1]
        image = link.find("img")
        team_name = clean_text(image.get("alt") if image else None)
        if not team_name:
            team_name = slug.replace("-", " ").title().replace("Rwe", "RWE").replace("Faze", "FaZe")
        teams[slug] = TeamRecord(
            source_system="overtime_elite",
            governing_body="OTE",
            team_name=team_name,
            team_slug=slug,
            roster_url=ote_roster_url(slug),
        )
    return [teams[slug] for slug in sorted(teams)]


def parse_ote_roster(team_slug: str, html: str, season_label: str) -> tuple[TeamRecord, list[RosterRow]]:
    source_url = ote_roster_url(team_slug)
    logger = get_logger(STAGE_PARSE)
    soup = BeautifulSoup(html, "html.parser")

    title = soup.find("meta", attrs={"property": "og:title"})
    team_name = clean_text(title["content"].removesuffix(" Roster")) if title and title.get("content") else None
    if not team_name:
        logger.error("Missing OTE team name source_url=%s parsing_stage=team_header", source_url)
        raise ValueError(f"Missing OTE team name for {source_url}")

    team = TeamRecord(
        source_system="overtime_elite",
        governing_body="OTE",
        team_name=team_name,
        team_slug=team_slug,
        roster_url=source_url,
    )
    rows: list[RosterRow] = []
    for card in soup.select("a.TeamPlayer[href^='/players/']"):
        href = card.get("href")
        profile_url = urljoin(OTE_BASE_URL, href)
        external_profile_id = profile_url.rstrip("/").rsplit("/", 1)[-1]

        image = card.find("img")
        first_name = clean_text(card.select_one(".FirstName").get_text()) if card.select_one(".FirstName") else None
        last_name = clean_text(card.select_one(".LastName").get_text()) if card.select_one(".LastName") else None
        image_name = clean_text(image.get("alt")) if image else None
        player_name = image_name or clean_text(f"{first_name or ''} {last_name or ''}")

        if not player_name or not external_profile_id:
            logger.error("Missing OTE player identity source_url=%s parsing_stage=player_card", source_url)
            raise ValueError(f"Missing OTE player identity for {source_url}")

        number = card.select_one(".Number")
        position = card.select_one(".Position")
        rows.append(
            RosterRow(
                source_system=team.source_system,
                governing_body=team.governing_body,
                source_url=source_url,
                parsing_stage="ote_roster",
                team_name=team.team_name,
                team_slug=team.team_slug,
                player_name=player_name,
                external_profile_id=external_profile_id,
                profile_url=profile_url,
                season_label=season_label,
                jersey_number=parse_int(number.get_text() if number else None),
                position=clean_text(position.get_text() if position else None),
            )
        )

    if not rows:
        logger.error("No OTE player cards found source_url=%s parsing_stage=player_cards", source_url)
        raise ValueError(f"No OTE roster rows found for {source_url}")

    return team, rows


def scrape_ote_rosters(season_label: str) -> tuple[list[TeamRecord], list[RosterRow], list[str]]:
    teams = discover_ote_teams()
    parsed_teams: dict[str, TeamRecord] = {team.team_slug: team for team in teams}
    rows: list[RosterRow] = []
    skipped: list[str] = []
    for team in teams:
        try:
            parsed_team, roster_rows = parse_ote_roster(
                team.team_slug,
                fetch_html(ote_roster_url(team.team_slug)),
                season_label,
            )
        except ValueError as exc:
            skipped.append(f"{team.team_slug}: {exc}")
            continue
        parsed_teams[team.team_slug] = parsed_team
        rows.extend(roster_rows)
    return list(parsed_teams.values()), rows, skipped


def eybl_roster_url(team_slug: str, season_label: str) -> str:
    return f"{EYBL_BASE_URL}/sports/mbball/{team_slug}/roster/{season_label}?path=mbball"


def extract_sidearm_components(html: str) -> list[dict[str, object]]:
    decoder = json.JSONDecoder()
    components: list[dict[str, object]] = []
    marker = "var component = "
    start = 0
    while True:
        index = html.find(marker, start)
        if index == -1:
            break
        json_start = index + len(marker)
        try:
            component, offset = decoder.raw_decode(html[json_start:])
        except json.JSONDecodeError:
            start = json_start
            continue
        if isinstance(component, dict):
            components.append(component)
        start = json_start + offset
    return components


def discover_eybl_teams() -> list[TeamRecord]:
    html = fetch_html(EYBL_BASE_URL + "/")
    roster_urls: dict[str, str] = {}

    def collect_roster_urls(value: object) -> None:
        if isinstance(value, dict):
            title = clean_text(str(value.get("title") or ""))
            url = clean_text(str(value.get("url") or ""))
            if title and url and "/roster/2025-26" in url:
                roster_urls[normalize_label(title)] = urljoin(EYBL_BASE_URL, url)
            for child in value.values():
                collect_roster_urls(child)
        elif isinstance(value, list):
            for child in value:
                collect_roster_urls(child)

    components = extract_sidearm_components(html)
    for component in components:
        collect_roster_urls(component)

    teams: dict[str, TeamRecord] = {}
    for component in components:
        if component.get("type") != "members":
            continue
        for item in component.get("data") or []:
            if not isinstance(item, dict):
                continue
            slug = clean_text(str(item.get("shortname") or ""))
            title = clean_text(str(item.get("title") or ""))
            if not slug or not title:
                continue
            roster_url = find_eybl_nav_roster_url(title, roster_urls)
            teams[slug] = TeamRecord(
                source_system="eybl_scholastic",
                governing_body="EYBL Scholastic",
                team_name=title,
                team_slug=slug,
                roster_url=roster_url,
            )
    return [teams[slug] for slug in sorted(teams)]


def normalize_label(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def find_eybl_nav_roster_url(team_name: str, roster_urls: dict[str, str]) -> str | None:
    normalized_team = normalize_label(team_name)
    if normalized_team in roster_urls:
        return roster_urls[normalized_team]
    for title, roster_url in roster_urls.items():
        if title.startswith(normalized_team) or normalized_team.startswith(title):
            return roster_url
    return None


def eybl_roster_matches_team(h1_text: str | None, team: TeamRecord, season_label: str) -> bool:
    if not h1_text or not h1_text.startswith(season_label):
        return False
    normalized_h1 = h1_text.lower()
    title = team.team_name.lower().strip()
    return title in normalized_h1


def parse_eybl_roster(team: TeamRecord, html: str, season_label: str) -> list[RosterRow]:
    source_url = team.roster_url or eybl_roster_url(team.team_slug, season_label)
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    h1_text = clean_text(h1.get_text(" ", strip=True) if h1 else None)
    if not eybl_roster_matches_team(h1_text, team, season_label):
        raise ValueError(f"EYBL roster unavailable or mismatched h1={h1_text!r}")

    rows: list[RosterRow] = []
    for player in soup.select("li.sidearm-roster-player"):
        player_id = clean_text(player.get("data-player-id"))
        player_path = clean_text(player.get("data-player-url"))
        profile_url = urljoin(EYBL_BASE_URL, player_path or "")

        name_node = player.select_one(".sidearm-roster-player-name a")
        image = player.find("img")
        player_name = clean_text(name_node.get_text(" ", strip=True) if name_node else None)
        if not player_name and image:
            player_name = clean_text(image.get("alt"))

        if not player_name or not player_id:
            get_logger(STAGE_PARSE).error("Missing EYBL player identity source_url=%s parsing_stage=player_card", source_url)
            raise ValueError(f"Missing EYBL player identity for {source_url}")

        position_node = player.select_one(".sidearm-roster-player-position-long-short")
        if position_node and "hide-on-medium" in position_node.get("class", []):
            position_node = player.select_one(".sidearm-roster-player-position-long-short:not(.hide-on-medium)")

        class_values = [
            clean_text(node.get_text(" ", strip=True))
            for node in player.select(".sidearm-roster-player-academic-year")
        ]
        class_text = next((value for value in class_values if value), None)
        grade_level = parse_grade_level(class_text)

        rows.append(
            RosterRow(
                source_system=team.source_system,
                governing_body=team.governing_body,
                source_url=source_url,
                parsing_stage="eybl_roster",
                team_name=team.team_name,
                team_slug=team.team_slug,
                player_name=player_name,
                external_profile_id=player_id,
                profile_url=profile_url,
                season_label=season_label,
                jersey_number=parse_int(
                    player.select_one(".sidearm-roster-player-jersey-number").get_text()
                    if player.select_one(".sidearm-roster-player-jersey-number")
                    else None
                ),
                position=clean_text(position_node.get_text(" ", strip=True) if position_node else None),
                expected_grad_year=expected_grad_year_from_grade(season_label, grade_level),
                grade_level=grade_level,
                height_inches=parse_height_inches(
                    player.select_one(".sidearm-roster-player-height").get_text()
                    if player.select_one(".sidearm-roster-player-height")
                    else None
                ),
            )
        )

    if not rows:
        raise ValueError(f"No EYBL roster rows found for {source_url}")
    return rows


def scrape_eybl_rosters(season_label: str) -> tuple[list[TeamRecord], list[RosterRow], list[str]]:
    teams = discover_eybl_teams()
    rows: list[RosterRow] = []
    skipped: list[str] = []
    for team in teams:
        source_url = team.roster_url or eybl_roster_url(team.team_slug, season_label)
        try:
            rows.extend(parse_eybl_roster(team, fetch_html(source_url), season_label))
        except ValueError as exc:
            fallback_url = eybl_roster_url(team.team_slug, season_label)
            if source_url != fallback_url:
                try:
                    rows.extend(parse_eybl_roster(replace(team, roster_url=fallback_url), fetch_html(fallback_url), season_label))
                    continue
                except ValueError:
                    pass
            skipped.append(f"{team.team_slug}: {exc}")
    return teams, rows, skipped


def scrape_rosters(source: str, season_label: str) -> tuple[list[TeamRecord], list[RosterRow], list[str]]:
    if source == "ote":
        return scrape_ote_rosters(season_label)
    if source == "eybl":
        return scrape_eybl_rosters(season_label)

    all_teams: list[TeamRecord] = []
    all_rows: list[RosterRow] = []
    all_skipped: list[str] = []
    for source_name in ("ote", "eybl"):
        teams, rows, skipped = scrape_rosters(source_name, season_label)
        all_teams.extend(teams)
        all_rows.extend(rows)
        all_skipped.extend([f"{source_name}:{item}" for item in skipped])
    return all_teams, all_rows, all_skipped


def upsert_teams(conn, teams: Iterable[TeamRecord]) -> dict[tuple[str, str], int]:
    team_ids: dict[tuple[str, str], int] = {}
    for team in teams:
        team_key = (team.governing_body, team.team_name)
        if team_key in team_ids:
            continue
        team_ids[team_key] = conn.execute(
            text(
                """
                insert into teams (name, governing_body, state_code)
                values (:name, :governing_body, null)
                on conflict (governing_body, name) do update
                set name = excluded.name
                returning id
                """
            ),
            {"name": team.team_name, "governing_body": team.governing_body},
        ).scalar_one()
    return team_ids


def upsert_rosters(teams: Iterable[TeamRecord], rows: Iterable[RosterRow]) -> dict[str, int]:
    from app.db import engine

    logger = get_logger(STAGE_DB_MAP)
    rows = list(rows)
    seen_sources: set[str] = set()
    seen_players: set[tuple[str, str]] = set()
    seen_rosters: set[tuple[str, str, str, str]] = set()

    with engine.begin() as conn:
        source_ids: dict[str, int] = {}
        team_ids = upsert_teams(conn, teams)

        for row in rows:
            source_id = source_ids.get(row.source_url)
            if source_id is None:
                source_id = conn.execute(
                    text(
                        """
                        insert into sources (url, source_system, fetched_at, parsing_stage)
                        values (:url, :source_system, now(), :parsing_stage)
                        on conflict (url) do update
                        set fetched_at = excluded.fetched_at,
                            source_system = excluded.source_system,
                            parsing_stage = excluded.parsing_stage
                        returning id
                        """
                    ),
                    {
                        "url": row.source_url,
                        "source_system": row.source_system,
                        "parsing_stage": row.parsing_stage,
                    },
                ).scalar_one()
                source_ids[row.source_url] = source_id

            team_key = (row.governing_body, row.team_name)
            team_id = team_ids.get(team_key)
            if team_id is None:
                team_id = upsert_teams(
                    conn,
                    [
                        TeamRecord(
                            source_system=row.source_system,
                            governing_body=row.governing_body,
                            team_name=row.team_name,
                            team_slug=row.team_slug,
                            roster_url=row.source_url,
                        )
                    ],
                )[team_key]
                team_ids[team_key] = team_id

            player_id = conn.execute(
                text(
                    """
                    insert into players (
                        full_name,
                        expected_grad_year,
                        external_source_id,
                        source_system,
                        source_profile_url
                    )
                    values (
                        :full_name,
                        :expected_grad_year,
                        :external_source_id,
                        :source_system,
                        :source_profile_url
                    )
                    on conflict (source_system, external_source_id) do update
                    set full_name = excluded.full_name,
                        expected_grad_year = excluded.expected_grad_year,
                        source_profile_url = excluded.source_profile_url
                    returning id
                    """
                ),
                {
                    "full_name": row.player_name,
                    "expected_grad_year": row.expected_grad_year,
                    "external_source_id": row.external_profile_id,
                    "source_system": row.source_system,
                    "source_profile_url": row.profile_url,
                },
            ).scalar_one()

            conn.execute(
                text(
                    """
                    insert into rosters (
                        player_id,
                        team_id,
                        season_label,
                        jersey_number,
                        position,
                        grade_level,
                        height_inches
                    )
                    values (
                        :player_id,
                        :team_id,
                        :season_label,
                        :jersey_number,
                        :position,
                        :grade_level,
                        :height_inches
                    )
                    on conflict (player_id, team_id, season_label) do update
                    set jersey_number = excluded.jersey_number,
                        position = excluded.position,
                        grade_level = excluded.grade_level,
                        height_inches = excluded.height_inches
                    returning id
                    """
                ),
                {
                    "player_id": player_id,
                    "team_id": team_id,
                    "season_label": row.season_label,
                    "jersey_number": row.jersey_number,
                    "position": row.position,
                    "grade_level": row.grade_level,
                    "height_inches": row.height_inches,
                },
            ).scalar_one()

            logger.info(
                "Mapped roster row source_id=%s team_id=%s player_id=%s source_url=%s",
                source_id,
                team_id,
                player_id,
                row.source_url,
            )

            seen_sources.add(row.source_url)
            seen_players.add((row.source_system, row.external_profile_id))
            seen_rosters.add((row.source_system, row.external_profile_id, row.team_slug, row.season_label))

    unique_teams = {(team.governing_body, team.team_name) for team in teams}
    return {
        "sources": len(seen_sources),
        "teams": len(unique_teams),
        "players": len(seen_players),
        "rosters": len(seen_rosters),
    }


def build_payload(teams: list[TeamRecord], rows: list[RosterRow], skipped: list[str]) -> dict[str, object]:
    return {
        "team_count": len({(team.governing_body, team.team_name) for team in teams}),
        "player_count": len(rows),
        "roster_count": len(rows),
        "skipped_roster_count": len(skipped),
        "teams": [asdict(team) for team in sorted(teams, key=lambda item: (item.governing_body, item.team_name))],
        "rows": [asdict(row) for row in rows],
        "skipped_rosters": skipped,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Sprint 1 circuit roster rows for S1-007.")
    parser.add_argument("--season-label", default=DEFAULT_SEASON_LABEL)
    parser.add_argument("--source", choices=("ote", "eybl", "all"), default="all")
    parser.add_argument("--load", action="store_true", help="Upsert rows into the configured database.")
    args = parser.parse_args()

    teams, rows, skipped = scrape_rosters(args.source, args.season_label)
    print(json.dumps(build_payload(teams, rows, skipped), indent=2, sort_keys=True))

    if args.load:
        counts = upsert_rosters(teams, rows)
        print(json.dumps({"upserted": counts}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
