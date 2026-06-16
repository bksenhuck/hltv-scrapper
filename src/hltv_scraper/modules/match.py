import re

from bs4 import BeautifulSoup, Tag
from playwright.async_api import Page

from ..conf.settings import (
    PAGE_TIMEOUT_MS,
    SEL_MAP_HOLDER,
    SEL_MAP_NAME,
    SEL_MAP_SCORE,
    SEL_MATCH_DATE,
    SEL_MATCH_EVENT,
    SEL_MATCH_FORMAT,
    SEL_MATCH_STAGE,
    SEL_MATCH_STATS,
    SEL_MATCH_TIME,
    SEL_PLAYER_NICK,
    SEL_STAT_ADR,
    SEL_STAT_KD,
    SEL_STAT_KAST,
    SEL_STAT_RATING,
    SEL_STATS_TABLE,
    SEL_STATS_TABLE_CT,
    SEL_STATS_TABLE_T,
    SELECTOR_TIMEOUT_MS,
)
from ..models import MapResult, MatchDetail, MatchResult, PlayerStat
from ..utils.log import get_logger, log_call
from ..utils.parsers import extract_match_id

log = get_logger(__name__)


@log_call
async def scrape_match_detail(page: Page, match: MatchResult) -> MatchDetail | None:
    if not match.match_url:
        return None

    match_id = extract_match_id(match.match_url)
    if match_id is None:
        log.warning("match_id not found in: %s", match.match_url)
        return None

    log.debug("Fetching match_id=%d  %s vs %s", match_id, match.team1.name, match.team2.name)

    try:
        await page.goto(match.match_url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except Exception as e:
        log.warning("match_id=%d: page.goto failed (%s) — skipping", match_id, e)
        return None

    try:
        await page.wait_for_selector(SEL_MAP_HOLDER, timeout=SELECTOR_TIMEOUT_MS)
    except Exception:
        log.debug("match_id=%d: no mapholder found (walkover or old match)", match_id)

    html = await page.content()
    detail = _parse_detail(html, match_id, match)
    log.debug(
        "match_id=%d: %d map(s), format=%s, stage=%s",
        match_id, len(detail.maps), detail.format, detail.stage,
    )
    return detail


# ── parsers ──────────────────────────────────────────────────────────────────

def _parse_detail(html: str, match_id: int, match: MatchResult) -> MatchDetail:
    soup = BeautifulSoup(html, "html.parser")

    match_time = _text(soup, SEL_MATCH_DATE)
    if not match_time:
        match_time = _text(soup, SEL_MATCH_TIME)

    event = _text(soup, SEL_MATCH_EVENT) or match.event
    stage = _parse_stage(soup)
    fmt   = _parse_format(soup)
    maps  = _parse_maps(soup, match)

    return MatchDetail(
        match_id=match_id,
        date=match.date,
        match_time=match_time,
        team1=match.team1.name,
        team2=match.team2.name,
        score_team1=match.team1.score,
        score_team2=match.team2.score,
        event=event,
        stage=stage,
        format=fmt,
        maps=maps,
        match_url=match.match_url,
    )


def _parse_maps(soup: BeautifulSoup, match: MatchResult) -> list[MapResult]:
    """Build a list of MapResult entries including an "all" aggregate (order=0).

    Stats are in .matchstats > .stats-content sections (not inside .mapholder).
    sections[0] = all-maps aggregate; sections[1:] align with mapholder order.
    Map names and per-map scores come from the .mapholder elements.
    """
    maps: list[MapResult] = []

    matchstats = soup.select_one(SEL_MATCH_STATS)
    if matchstats is None:
        log.debug("No .matchstats element found — old match with no player stats")
        return maps

    # Direct-child .stats-content divs (avoid nested false positives)
    sections = [
        c for c in matchstats.children
        if getattr(c, "name", None) == "div" and "stats-content" in c.get("class", [])
    ]
    if not sections:
        return maps

    # --- All Maps aggregate (order=0) ---
    t1b, t2b, t1ct, t2ct, t1t, t2t = _parse_stats_section(sections[0])
    maps.append(MapResult(
        order=0,
        name="all",
        score_team1=match.team1.score,
        score_team2=match.team2.score,
        players_team1=t1b,
        players_team2=t2b,
        players_team1_ct=t1ct,
        players_team2_ct=t2ct,
        players_team1_t=t1t,
        players_team2_t=t2t,
    ))

    # --- Per-map entries (order=1, 2, ...) ---
    map_sections = sections[1:]  # aligned with mapholder list by index
    for order, holder in enumerate(soup.select(SEL_MAP_HOLDER), start=1):
        name_el = holder.select_one(SEL_MAP_NAME)
        if not name_el:
            continue

        map_name = name_el.get_text(strip=True)
        if map_name.lower() in ("tba", ""):
            continue

        scores = holder.select(SEL_MAP_SCORE)
        if len(scores) < 2:
            continue
        try:
            s1 = int(scores[0].get_text(strip=True))
            s2 = int(scores[1].get_text(strip=True))
        except ValueError:
            continue

        idx = order - 1  # sections[0] is all-maps, so map 1 → index 0 in map_sections
        if idx < len(map_sections):
            t1b, t2b, t1ct, t2ct, t1t, t2t = _parse_stats_section(map_sections[idx])
        else:
            t1b = t2b = t1ct = t2ct = t1t = t2t = []

        maps.append(MapResult(
            order=order,
            name=map_name,
            score_team1=s1,
            score_team2=s2,
            players_team1=t1b,
            players_team2=t2b,
            players_team1_ct=t1ct,
            players_team2_ct=t2ct,
            players_team1_t=t1t,
            players_team2_t=t2t,
        ))

    return maps


def _parse_stats_section(
    section: Tag,
) -> tuple[list[PlayerStat], list[PlayerStat], list[PlayerStat], list[PlayerStat], list[PlayerStat], list[PlayerStat]]:
    """Return (t1_both, t2_both, t1_ct, t2_ct, t1_t, t2_t) from a stats-content div."""
    total_tables = section.find_all("table", class_="totalstats")
    ct_tables    = section.find_all("table", class_="ctstats")
    t_tables     = section.find_all("table", class_="tstats")

    t1_both = _parse_player_table(total_tables[0] if len(total_tables) > 0 else None)
    t2_both = _parse_player_table(total_tables[1] if len(total_tables) > 1 else None)
    t1_ct   = _parse_player_table(ct_tables[0]    if len(ct_tables)    > 0 else None)
    t2_ct   = _parse_player_table(ct_tables[1]    if len(ct_tables)    > 1 else None)
    t1_t    = _parse_player_table(t_tables[0]     if len(t_tables)     > 0 else None)
    t2_t    = _parse_player_table(t_tables[1]     if len(t_tables)     > 1 else None)

    return t1_both, t2_both, t1_ct, t2_ct, t1_t, t2_t


def _parse_player_table(table: Tag | None) -> list[PlayerStat]:
    if table is None:
        return []
    players: list[PlayerStat] = []

    for row in table.select("tbody tr"):
        nick_el = row.select_one(SEL_PLAYER_NICK)
        if not nick_el:
            continue  # header row has no .player-nick

        name = nick_el.get_text(strip=True)
        if not name:
            continue

        kills, deaths = _parse_kd(row.select(SEL_STAT_KD))
        adr    = _float_cell(_trad_cell(row.select(SEL_STAT_ADR)))
        kast   = _float_pct(_trad_cell(row.select(SEL_STAT_KAST)))
        rating = _float_cell(row.select_one(SEL_STAT_RATING))

        players.append(PlayerStat(name=name, kills=kills, deaths=deaths, adr=adr, kast=kast, rating=rating))

    return players


def _parse_stage(soup: BeautifulSoup) -> str | None:
    el = soup.select_one(SEL_MATCH_STAGE)
    if el:
        return el.get_text(strip=True) or None
    banner = soup.select_one(".timeAndEvent")
    if banner:
        text = banner.get_text(" ", strip=True)
        m = re.search(r"(Quarter|Semi|Grand\s*Final|Final|Group\s*Stage|Play[- ]?[Oo]ff)", text)
        if m:
            return m.group(0)
    return None


def _parse_format(soup: BeautifulSoup) -> str | None:
    el = soup.select_one(SEL_MATCH_FORMAT)
    if el:
        text = el.get_text(" ", strip=True)
        m = re.search(r"[Bb]est\s+of\s+(\d)", text)
        if m:
            return f"bo{m.group(1)}"
    text = soup.get_text(" ", strip=True)
    m = re.search(r"[Bb]est\s+of\s+(\d)", text)
    return f"bo{m.group(1)}" if m else None


# ── helpers ───────────────────────────────────────────────────────────────────

def _text(soup: BeautifulSoup, selector: str) -> str | None:
    el = soup.select_one(selector)
    return el.get_text(strip=True) or None if el else None


def _trad_cell(cells: list) -> Tag | None:
    """Return the traditional-data cell (non-eco-adjusted) from a list of matching cells."""
    return next(
        (c for c in cells if "traditional-data" in c.get("class", [])),
        cells[0] if cells else None,
    )


def _parse_kd(cells: list) -> tuple[int | None, int | None]:
    """Parse kills/deaths from td.kd cells. Format: '46-23' in the traditional-data cell."""
    cell = _trad_cell(cells)
    if cell is None:
        return None, None
    text = cell.get_text(strip=True)
    if "-" not in text:
        return None, None
    parts = text.split("-")
    try:
        return int(parts[0].strip()), int(parts[1].strip())
    except (ValueError, IndexError):
        return None, None


def _float_cell(el: Tag | None) -> float | None:
    if el is None:
        return None
    try:
        return float(el.get_text(strip=True))
    except ValueError:
        return None


def _float_pct(el: Tag | None) -> float | None:
    """Convert '72.7%' → 72.7."""
    if el is None:
        return None
    try:
        return float(el.get_text(strip=True).replace("%", ""))
    except ValueError:
        return None
