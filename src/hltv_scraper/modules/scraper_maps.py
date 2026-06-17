"""Parse map-level data (map names, per-map scores) from a match page HTML."""
from bs4 import BeautifulSoup

from ..conf.settings import SEL_MAP_HOLDER, SEL_MAP_NAME, SEL_MAP_SCORE
from .common import get_stats_sections


def parse_map_rows(
    html: str,
    match_id: int,
    series_score_t1: int,
    series_score_t2: int,
) -> list[dict]:
    """Return dicts ready for maps.parquet.

    map_order=0 is the "all maps" aggregate (uses series scores).
    map_order=1+ are individual maps parsed from the mapholder elements.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[dict] = []

    sections = get_stats_sections(soup)
    if sections:
        rows.append({
            "match_id":    match_id,
            "map_order":   0,
            "map_name":    "all",
            "score_team1": series_score_t1,
            "score_team2": series_score_t2,
        })

    for order, holder in enumerate(soup.select(SEL_MAP_HOLDER), start=1):
        name_el = holder.select_one(SEL_MAP_NAME)
        if not name_el:
            continue
        map_name = name_el.get_text(strip=True)
        if map_name.lower() in ("tba", ""):
            continue
        scores = holder.select(SEL_MAP_SCORE)
        try:
            s1 = int(scores[0].get_text(strip=True)) if len(scores) >= 1 else 0
            s2 = int(scores[1].get_text(strip=True)) if len(scores) >= 2 else 0
        except ValueError:
            s1, s2 = 0, 0
        rows.append({
            "match_id":    match_id,
            "map_order":   order,
            "map_name":    map_name,
            "score_team1": s1,
            "score_team2": s2,
        })

    return rows
