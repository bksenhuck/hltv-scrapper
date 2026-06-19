"""Low-level HTML parsing helpers shared by all scraper modules."""
from bs4 import BeautifulSoup, Tag

from ..conf.settings import SEL_MATCH_STATS


def get_stats_sections(soup: BeautifulSoup) -> list[Tag]:
    """Return direct-child .stats-content divs from .matchstats.

    sections[0] = All Maps aggregate; sections[1:] = per-map (aligned with mapholders).
    """
    matchstats = soup.select_one(SEL_MATCH_STATS)
    if matchstats is None:
        return []
    return [
        c for c in matchstats.children
        if getattr(c, "name", None) == "div" and "stats-content" in c.get("class", [])
    ]


def trad_cell(cells: list) -> Tag | None:
    """Return the traditional-data cell (non-eco-adjusted) from a list of matching cells."""
    return next(
        (c for c in cells if "traditional-data" in c.get("class", [])),
        cells[0] if cells else None,
    )


def parse_kd(cells: list) -> tuple[int | None, int | None]:
    """Parse kills/deaths from td.kd cells. Format: '46-23' in the traditional-data cell."""
    cell = trad_cell(cells)
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


def float_cell(el: Tag | None) -> float | None:
    if el is None:
        return None
    try:
        return float(el.get_text(strip=True))
    except ValueError:
        return None


def float_pct(el: Tag | None) -> float | None:
    """Convert '72.7%' → 72.7."""
    if el is None:
        return None
    try:
        return float(el.get_text(strip=True).replace("%", ""))
    except ValueError:
        return None
