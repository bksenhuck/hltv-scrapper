"""Parse player stats (kills, deaths, ADR, KAST, rating) from a match page HTML."""
from bs4 import BeautifulSoup, Tag

from ...conf.settings import (
    SEL_PLAYER_NICK,
    SEL_STAT_ADR,
    SEL_STAT_KD,
    SEL_STAT_KAST,
    SEL_STAT_RATING,
)
from ...utils.html import float_cell, float_pct, get_stats_sections, parse_kd, trad_cell


def parse_stat_rows(html: str, match_id: int) -> list[dict]:
    """Return dicts ready for player_stats.parquet.

    map_order mirrors the sections index: 0 = All Maps aggregate, 1+ = per-map.
    Each row has team (1 or 2) and side ('both' | 'ct' | 't').
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []
    for map_order, section in enumerate(get_stats_sections(soup)):
        rows.extend(_section_rows(section, match_id, map_order))
    return rows


def _section_rows(section: Tag, match_id: int, map_order: int) -> list[dict]:
    total_tables = section.find_all("table", class_="totalstats")
    ct_tables    = section.find_all("table", class_="ctstats")
    t_tables     = section.find_all("table", class_="tstats")

    rows: list[dict] = []
    for team_idx, (t_total, t_ct, t_t) in enumerate(_zip_team_tables(total_tables, ct_tables, t_tables), start=1):
        for side, table in [("both", t_total), ("ct", t_ct), ("t", t_t)]:
            if table is None:
                continue
            rows.extend(_table_rows(table, match_id, map_order, team_idx, side))
    return rows


def _zip_team_tables(total: list, ct: list, t: list):
    """Yield (total_table, ct_table, t_table) for team1 then team2."""
    for i in range(2):
        yield (
            total[i] if i < len(total) else None,
            ct[i]    if i < len(ct)    else None,
            t[i]     if i < len(t)     else None,
        )


def _table_rows(table: Tag, match_id: int, map_order: int, team: int, side: str) -> list[dict]:
    rows: list[dict] = []
    for tr in table.select("tbody tr"):
        nick_el = tr.select_one(SEL_PLAYER_NICK)
        if not nick_el:
            continue
        name = nick_el.get_text(strip=True)
        if not name:
            continue
        kills, deaths = parse_kd(tr.select(SEL_STAT_KD))
        rows.append({
            "match_id":    match_id,
            "map_order":   map_order,
            "team":        team,
            "side":        side,
            "player_name": name,
            "kills":       kills,
            "deaths":      deaths,
            "adr":         float_cell(trad_cell(tr.select(SEL_STAT_ADR))),
            "kast":        float_pct(trad_cell(tr.select(SEL_STAT_KAST))),
            "rating":      float_cell(tr.select_one(SEL_STAT_RATING)),
        })
    return rows
