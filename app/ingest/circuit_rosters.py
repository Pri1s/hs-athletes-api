from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from sqlalchemy import text

from app.ingest.box_score_contract import BoxScoreGame, BoxScorePlayerStats, validate_box_score_rows
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


def parse_stat_int(value: str | None) -> int | None:
    cleaned = clean_text(value)
    if cleaned is None:
        return None
    cleaned = cleaned.rstrip("+")
    if not cleaned.isdigit():
        return None
    return int(cleaned)


def parse_stat_pair(value: str | None) -> tuple[int | None, int | None]:
    cleaned = clean_text(value)
    if cleaned is None or "-" not in cleaned:
        return None, None
    made, attempted = cleaned.split("-", 1)
    return parse_stat_int(made), parse_stat_int(attempted)


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


def raise_parse_error(source_url: str, parsing_stage: str, message: str) -> None:
    get_logger(STAGE_PARSE).error("%s source_url=%s parsing_stage=%s", message, source_url, parsing_stage)
    raise ValueError(f"{message} for {source_url}")


def log_parse_warning(source_url: str, parsing_stage: str, message: str) -> None:
    get_logger(STAGE_PARSE).warning("%s source_url=%s parsing_stage=%s", message, source_url, parsing_stage)


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


def scrape_ote_player_index(season_label: str) -> list[RosterRow]:
    source_url = f"{OTE_BASE_URL}/players"
    soup = BeautifulSoup(fetch_html(source_url), "html.parser")
    rows: dict[str, RosterRow] = {}
    for link in soup.select("a[href^='/players/']"):
        href = clean_text(link.get("href"))
        if not href:
            continue
        profile_url = urljoin(OTE_BASE_URL, href)
        external_profile_id = profile_url.rstrip("/").rsplit("/", 1)[-1]
        image = link.find("img")
        player_name = clean_text(image.get("alt") if image else None)
        if not player_name:
            link_text = clean_text(link.get_text(" ", strip=True))
            player_name = re.sub(r"^\d+\s+", "", link_text or "")
            player_name = player_name.split(" Guard ")[0].split(" Forward ")[0].split(" Center ")[0]
            player_name = clean_text(player_name)
        if not player_name or not external_profile_id:
            continue
        rows[external_profile_id] = RosterRow(
            source_system="overtime_elite",
            governing_body="OTE",
            source_url=source_url,
            parsing_stage="ote_player_index",
            team_name="OTE",
            team_slug="players",
            player_name=player_name,
            external_profile_id=external_profile_id,
            profile_url=profile_url,
            season_label=season_label,
            jersey_number=None,
            position=None,
        )
    if not rows:
        raise_parse_error(source_url, "ote_player_index", "No OTE player index rows found")
    return list(rows.values())


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
        raise_parse_error(source_url, "eybl_roster_header", f"EYBL roster unavailable or mismatched h1={h1_text!r}")

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
            raise_parse_error(source_url, "player_card", "Missing EYBL player identity")

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
        raise_parse_error(source_url, "eybl_roster_rows", "No EYBL roster rows found")
    return rows


def eybl_box_score_external_game_id(source_url: str) -> str | None:
    values = parse_qs(urlparse(source_url).query).get("id")
    if not values:
        return None
    return values[0]


def normalize_player_name(value: str | None) -> str | None:
    cleaned = clean_text(value)
    if not cleaned:
        return None
    if "," in cleaned:
        last_name, first_name = [part.strip() for part in cleaned.split(",", 1)]
        cleaned = clean_text(f"{first_name} {last_name}") or cleaned
    return cleaned


def player_identity_matches_team(identity: RosterRow, team_name: str) -> bool:
    normalized_team = normalize_label(team_name)
    identity_team = normalize_label(identity.team_name)
    identity_slug = normalize_label(identity.team_slug)
    return (
        normalized_team == identity_team
        or normalized_team == identity_slug
        or identity_team.startswith(normalized_team)
        or normalized_team.startswith(identity_team)
    )


def find_player_identity(
    player_name: str,
    team_name: str,
    player_identities: Iterable[RosterRow],
) -> RosterRow | None:
    normalized_player = normalize_label(player_name)
    candidates = [
        identity
        for identity in player_identities
        if normalize_label(identity.player_name) == normalized_player
    ]
    team_candidates = [identity for identity in candidates if player_identity_matches_team(identity, team_name)]
    if len(team_candidates) == 1:
        return team_candidates[0]
    if len(candidates) == 1:
        return candidates[0]
    return None


def json_ld_objects(soup: BeautifulSoup) -> list[dict[str, object]]:
    objects: list[dict[str, object]] = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            payload = json.loads(script.string or "")
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            objects.append(payload)
        elif isinstance(payload, list):
            objects.extend(item for item in payload if isinstance(item, dict))
    return objects


def ote_box_score_external_game_id(source_url: str) -> str | None:
    match = re.search(r"/games/([^/]+)", urlparse(source_url).path)
    if not match:
        return None
    return match.group(1)


def ote_box_score_game_date(soup: BeautifulSoup, source_url: str):
    for item in json_ld_objects(soup):
        if item.get("@type") != "SportsEvent":
            continue
        start_date = clean_text(str(item.get("startDate") or ""))
        if start_date:
            return datetime.fromisoformat(start_date.replace("Z", "+00:00")).date()

    time_node = soup.find("time")
    date_time = clean_text(time_node.get("datetime") if time_node else None)
    if date_time:
        return datetime.fromisoformat(date_time.replace("Z", "+00:00")).date()
    raise_parse_error(source_url, "ote_box_score_game_date", "Missing OTE box score date")


def ote_box_score_team_names(soup: BeautifulSoup, source_url: str) -> list[str]:
    for table in soup.find_all("table"):
        header_labels = [
            normalize_label(header.get_text(" ", strip=True))
            for header in table.find_all("th")
        ]
        if "t total" not in header_labels and "total" not in header_labels:
            continue

        team_names = []
        for row in table.find_all("tr")[1:]:
            team_cell = row.find("th")
            if team_cell is None:
                continue
            desktop_name = team_cell.select_one(".desktop-only")
            team_name = clean_text(desktop_name.get_text(" ", strip=True) if desktop_name else None)
            if not team_name:
                team_name = clean_text(team_cell.get_text(" ", strip=True))
            if team_name:
                team_names.append(team_name)
        if len(team_names) >= 2:
            return team_names[:2]
    raise_parse_error(source_url, "ote_box_score_team_summary", "Missing OTE box score team summary")


def ote_stat_header_labels(table) -> list[str]:
    header_row = table.find("tr")
    if header_row is None:
        return []
    labels = []
    for cell in header_row.find_all(["th", "td"]):
        label = clean_text(cell.get_text(" ", strip=True))
        labels.append(label.lower().split()[0] if label else "")
    return labels


def ote_box_score_player_name(row) -> str | None:
    player_header = row.find("th")
    if player_header is None:
        return None
    name_node = player_header.select_one(".Name")
    image = player_header.find("img", attrs={"alt": True})
    player_name = clean_text(name_node.get_text(" ", strip=True) if name_node else None)
    if not player_name and image:
        player_name = clean_text(image.get("alt"))
    if not player_name:
        player_name = clean_text(player_header.get_text(" ", strip=True))
    if not player_name:
        return None
    return clean_text(re.sub(r"^\d+\s+", "", player_name))


def is_ote_team_total_row(player_name: str, team_name: str) -> bool:
    normalized_player = normalize_label(player_name)
    normalized_team = normalize_label(team_name)
    return normalized_player == normalized_team or normalized_team.endswith(normalized_player)


def parse_ote_box_score(
    html: str,
    source_url: str,
    player_identities: Iterable[RosterRow],
    skip_unresolved_identities: bool = False,
) -> list[BoxScorePlayerStats]:
    soup = BeautifulSoup(html, "html.parser")
    game_date = ote_box_score_game_date(soup, source_url)
    team_names = ote_box_score_team_names(soup, source_url)
    identity_rows = list(player_identities)
    rows: list[BoxScorePlayerStats] = []
    stats_tables = [
        table
        for table in soup.find_all("table")
        if ote_stat_header_labels(table)[:2] == ["player", "pts"]
    ]

    for table, team_name in zip(stats_tables, team_names):
        opponent_name = next((name for name in team_names if normalize_label(name) != normalize_label(team_name)), None)
        if opponent_name is None:
            raise_parse_error(source_url, "ote_box_score_opponent", f"Missing opponent for OTE team {team_name}")

        game = BoxScoreGame(
            source_system="overtime_elite",
            source_url=source_url,
            game_date=game_date,
            team_name=team_name,
            opponent_name=opponent_name,
            external_game_id=ote_box_score_external_game_id(source_url),
        )

        labels = ote_stat_header_labels(table)
        for row in table.find_all("tr")[1:]:
            player_name = ote_box_score_player_name(row)
            if not player_name or is_ote_team_total_row(player_name, team_name):
                continue

            identity = find_player_identity(player_name, team_name, identity_rows)
            if identity is None:
                message = f"Missing OTE player identity for {team_name} {player_name}"
                if skip_unresolved_identities:
                    log_parse_warning(source_url, "ote_box_score_identity", message)
                    continue
                raise_parse_error(source_url, "ote_box_score_identity", message)

            cells = row.find_all("td")
            stat_values = {
                label: clean_text(cell.get_text(" ", strip=True))
                for label, cell in zip(labels[1:], cells)
                if label
            }
            rows.append(
                BoxScorePlayerStats(
                    game=game,
                    player_name=identity.player_name,
                    external_profile_id=identity.external_profile_id,
                    profile_url=identity.profile_url,
                    points=parse_stat_int(stat_values.get("pts")),
                    rebounds=parse_stat_int(stat_values.get("reb")),
                    assists=parse_stat_int(stat_values.get("ast")),
                    steals=parse_stat_int(stat_values.get("stl")),
                    blocks=parse_stat_int(stat_values.get("blk")),
                    minutes_played=parse_stat_int(stat_values.get("min")),
                    free_throws_made=parse_stat_int(stat_values.get("ftm")),
                    free_throws_attempted=parse_stat_int(stat_values.get("fta")),
                    turnovers=parse_stat_int(stat_values.get("to")),
                    fouls=parse_stat_int(stat_values.get("pf")),
                )
            )

    try:
        return validate_box_score_rows(rows)
    except (TypeError, ValueError) as exc:
        raise_parse_error(source_url, "ote_box_score_rows", str(exc))


def scrape_ote_box_score(source_url: str, season_label: str) -> list[BoxScorePlayerStats]:
    html = fetch_html(source_url)
    player_rows = scrape_ote_player_index(season_label)
    return parse_ote_box_score(html, source_url, player_rows, skip_unresolved_identities=True)


def eybl_box_score_team_names(soup: BeautifulSoup, source_url: str) -> list[str]:
    for table in soup.find_all("table"):
        caption = table.find("caption")
        if clean_text(caption.get_text(" ", strip=True) if caption else None) != "Team Score By Half":
            continue
        team_names = []
        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["th", "td"])
            team_name = clean_text(cells[0].get_text(" ", strip=True) if cells else None)
            if team_name:
                team_names.append(team_name)
        if len(team_names) >= 2:
            return team_names
    raise_parse_error(source_url, "box_score_team_summary", "Missing EYBL box score team summary")


def eybl_box_score_game_date(soup: BeautifulSoup, source_url: str):
    for label in soup.find_all("dt"):
        if clean_text(label.get_text(" ", strip=True)) != "Date":
            continue
        value = label.find_next_sibling("dd")
        date_text = clean_text(value.get_text(" ", strip=True) if value else None)
        if date_text:
            return datetime.strptime(date_text, "%m/%d/%Y").date()
    raise_parse_error(source_url, "box_score_game_date", "Missing EYBL box score date")


def eybl_box_score_player_name(row) -> str | None:
    player_header = row.find("th", scope="row")
    if player_header is None:
        return None
    for jersey in player_header.select(".mobile-jersey-number"):
        jersey.decompose()
    return normalize_player_name(player_header.get_text(" ", strip=True))


def parse_eybl_box_score(
    html: str,
    source_url: str,
    player_identities: Iterable[RosterRow],
    skip_unresolved_identities: bool = False,
) -> list[BoxScorePlayerStats]:
    soup = BeautifulSoup(html, "html.parser")
    game_date = eybl_box_score_game_date(soup, source_url)
    team_names = eybl_box_score_team_names(soup, source_url)
    identity_rows = list(player_identities)
    rows: list[BoxScorePlayerStats] = []

    for table in soup.find_all("table"):
        caption = table.find("caption")
        caption_text = clean_text(caption.get_text(" ", strip=True) if caption else None)
        if not caption_text or not caption_text.endswith(" - Team Statistics"):
            continue

        team_name = caption_text.removesuffix(" - Team Statistics")
        opponent_name = next((name for name in team_names if normalize_label(name) != normalize_label(team_name)), None)
        if opponent_name is None:
            raise_parse_error(source_url, "box_score_opponent", f"Missing opponent for EYBL team {team_name}")

        game = BoxScoreGame(
            source_system="eybl_scholastic",
            source_url=source_url,
            game_date=game_date,
            team_name=team_name,
            opponent_name=opponent_name,
            external_game_id=eybl_box_score_external_game_id(source_url),
        )

        for row in table.find_all("tr")[1:]:
            player_name = eybl_box_score_player_name(row)
            if not player_name or normalize_label(player_name) in {"totals", "team total"}:
                continue

            identity = find_player_identity(player_name, team_name, identity_rows)
            if identity is None:
                message = f"Missing EYBL player identity for {team_name} {player_name}"
                if skip_unresolved_identities:
                    log_parse_warning(source_url, "box_score_identity", message)
                    continue
                raise_parse_error(source_url, "box_score_identity", message)

            stat_values = {
                cell["data-label"]: clean_text(cell.get_text(" ", strip=True))
                for cell in row.find_all("td")
                if cell.get("data-label")
            }
            free_throws_made, free_throws_attempted = parse_stat_pair(stat_values.get("FT"))
            rows.append(
                BoxScorePlayerStats(
                    game=game,
                    player_name=identity.player_name,
                    external_profile_id=identity.external_profile_id,
                    profile_url=identity.profile_url,
                    points=parse_stat_int(stat_values.get("PTS")),
                    rebounds=parse_stat_int(stat_values.get("REB")),
                    assists=parse_stat_int(stat_values.get("A")),
                    steals=parse_stat_int(stat_values.get("STL")),
                    blocks=parse_stat_int(stat_values.get("BLK")),
                    minutes_played=parse_stat_int(stat_values.get("MIN")),
                    free_throws_made=free_throws_made,
                    free_throws_attempted=free_throws_attempted,
                    turnovers=parse_stat_int(stat_values.get("TO")),
                    fouls=parse_stat_int(stat_values.get("PF")),
                )
            )

    try:
        return validate_box_score_rows(rows)
    except (TypeError, ValueError) as exc:
        raise_parse_error(source_url, "box_score_rows", str(exc))


def find_eybl_team_for_box_score_name(team_name: str, teams: Iterable[TeamRecord]) -> TeamRecord | None:
    normalized_team = normalize_label(team_name)
    for team in teams:
        normalized_record_name = normalize_label(team.team_name)
        normalized_slug = normalize_label(team.team_slug)
        if (
            normalized_team == normalized_record_name
            or normalized_team == normalized_slug
            or normalized_record_name.startswith(normalized_team)
            or normalized_team.startswith(normalized_record_name)
        ):
            return team
    return None


def scrape_eybl_box_score(source_url: str, season_label: str) -> list[BoxScorePlayerStats]:
    html = fetch_html(source_url)
    soup = BeautifulSoup(html, "html.parser")
    box_score_team_names = eybl_box_score_team_names(soup, source_url)
    eybl_teams = discover_eybl_teams()
    roster_rows: list[RosterRow] = []

    for team_name in box_score_team_names:
        team = find_eybl_team_for_box_score_name(team_name, eybl_teams)
        if team is None:
            raise_parse_error(source_url, "box_score_team_roster", f"Missing EYBL roster team for {team_name}")
        roster_url = team.roster_url or eybl_roster_url(team.team_slug, season_label)
        roster_rows.extend(parse_eybl_roster(replace(team, roster_url=roster_url), fetch_html(roster_url), season_label))

    return parse_eybl_box_score(html, source_url, roster_rows, skip_unresolved_identities=True)


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


def box_score_row_payload(row: BoxScorePlayerStats) -> dict[str, object]:
    return {
        "game": {
            "source_system": row.game.source_system,
            "source_url": row.game.source_url,
            "external_game_id": row.game.external_game_id,
            "game_date": row.game.game_date.isoformat(),
            "team_name": row.game.team_name,
            "opponent_name": row.game.opponent_name,
        },
        "player_name": row.player_name,
        "external_profile_id": row.external_profile_id,
        "profile_url": row.profile_url,
        "points": row.points,
        "rebounds": row.rebounds,
        "assists": row.assists,
        "steals": row.steals,
        "blocks": row.blocks,
        "minutes_played": row.minutes_played,
        "free_throws_made": row.free_throws_made,
        "free_throws_attempted": row.free_throws_attempted,
        "turnovers": row.turnovers,
        "fouls": row.fouls,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Sprint 1 circuit roster and box-score rows.")
    parser.add_argument("--season-label", default=DEFAULT_SEASON_LABEL)
    parser.add_argument("--source", choices=("ote", "eybl", "all"), default="all")
    parser.add_argument("--load", action="store_true", help="Upsert rows into the configured database.")
    parser.add_argument("--eybl-box-score-url", help="Fetch one EYBL box-score page and emit S1-008 contract rows.")
    parser.add_argument("--ote-box-score-url", help="Fetch one OTE box-score page and emit S1-008 contract rows.")
    args = parser.parse_args()

    if args.eybl_box_score_url:
        rows = scrape_eybl_box_score(args.eybl_box_score_url, args.season_label)
        print(
            json.dumps(
                {
                    "box_score_row_count": len(rows),
                    "box_score_rows": [box_score_row_payload(row) for row in rows],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.ote_box_score_url:
        rows = scrape_ote_box_score(args.ote_box_score_url, args.season_label)
        print(
            json.dumps(
                {
                    "box_score_row_count": len(rows),
                    "box_score_rows": [box_score_row_payload(row) for row in rows],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    teams, rows, skipped = scrape_rosters(args.source, args.season_label)
    print(json.dumps(build_payload(teams, rows, skipped), indent=2, sort_keys=True))

    if args.load:
        counts = upsert_rosters(teams, rows)
        print(json.dumps({"upserted": counts}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
