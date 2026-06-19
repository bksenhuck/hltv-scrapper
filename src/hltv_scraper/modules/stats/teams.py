"""Scrape the HLTV /stats/teams page for a given filter combination."""
import re
from datetime import datetime, timezone
from itertools import product
from urllib.parse import urlencode

from bs4 import BeautifulSoup, Tag

from ...conf.settings import (
    HLTV_CURRENT_YEAR,
    HLTV_START_YEAR,
    SEL_STATS_TABLE,
    STATS_CS_VERSIONS,
    STATS_MAPS,
    STATS_MATCH_TYPES,
    STATS_TEAMS_URL,
)
from ...utils.log import get_logger

log = get_logger(__name__)

_ALL = "all"


def get_all_combinations() -> list[tuple]:
    """Return every (year, match_type, map_name, cs_version) tuple to scrape.

    year is either the string "all" (All time) or an int (HLTV_START_YEAR–HLTV_CURRENT_YEAR).
    """
    years = [_ALL] + list(range(HLTV_START_YEAR, HLTV_CURRENT_YEAR + 1))
    return list(product(years, STATS_MATCH_TYPES, STATS_MAPS, STATS_CS_VERSIONS))


def build_team_stats_url(year, match_type: str, map_name: str, cs_version: str) -> str:
    params: dict[str, str] = {"rankingFilter": "All"}

    if year == _ALL:
        params["startDate"] = "all"
    else:
        params["startDate"] = f"{year}-01-01"
        params["endDate"] = f"{year}-12-31"

    if match_type:
        params["matchType"] = match_type
    if map_name:
        params["maps"] = map_name
    if cs_version:
        params["csVersion"] = cs_version

    return f"{STATS_TEAMS_URL}?{urlencode(params)}"


def combo_key(year, match_type: str, map_name: str, cs_version: str) -> str:
    """Stable string key for a combination — used in progress tracking."""
    return f"{year}|{match_type or 'all'}|{map_name or 'all'}|{cs_version or 'both'}"


def parse_team_stats_table(
    html: str,
    year,
    match_type: str,
    map_name: str,
    cs_version: str,
) -> list[dict]:
    """Parse the stats table from a fetched HTML string.

    Returns a list of row dicts ready for Polars / Parquet.
    Empty list if the table is missing or has no rows.
    """
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one(SEL_STATS_TABLE)
    if table is None:
        log.debug("No stats table found (year=%s matchType=%s map=%s version=%s)",
                  year, match_type, map_name, cs_version)
        return []

    scraped_at = datetime.now(timezone.utc).isoformat()
    rows: list[dict] = []

    for rank, tr in enumerate(table.select("tbody tr"), start=1):
        cells = tr.find_all("td")
        if len(cells) < 5:
            continue

        team_cell = cells[0]
        a_tag      = team_cell.find("a")
        flag_img   = team_cell.find("img", class_="flag")

        team_name = a_tag.get_text(strip=True) if a_tag else ""
        team_href = a_tag.get("href", "") if a_tag else ""
        m = re.search(r"/stats/teams/(\d+)/", team_href)
        team_id = int(m.group(1)) if m else None
        country = flag_img.get("alt", "") if flag_img else ""

        rows.append({
            "year":        str(year),
            "match_type":  match_type or "all",
            "map_name":    map_name or "all",
            "cs_version":  cs_version or "both",
            "rank":        rank,
            "team_id":     team_id,
            "team_name":   team_name,
            "country":     country,
            "maps_played": _to_int(cells[1]),
            "kd_diff":     _parse_diff(cells[2].get_text(strip=True)),
            "kd_ratio":    _to_float(cells[3]),
            "rating":      _to_float(cells[4]),
            "scraped_at":  scraped_at,
        })

    return rows


def _to_int(cell: Tag | None) -> int | None:
    if cell is None:
        return None
    try:
        return int(cell.get_text(strip=True).replace(",", ""))
    except ValueError:
        return None


def _to_float(cell: Tag | None) -> float | None:
    if cell is None:
        return None
    try:
        return float(cell.get_text(strip=True))
    except ValueError:
        return None


def _parse_diff(text: str) -> int | None:
    try:
        return int(text.replace(",", "").replace("+", "").strip())
    except ValueError:
        return None
