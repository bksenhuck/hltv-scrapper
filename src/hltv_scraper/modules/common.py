"""Shared browser interaction and low-level HTML parse helpers used by all scraper modules."""
from bs4 import BeautifulSoup, Tag
from playwright.async_api import Page

from ..conf.settings import PAGE_TIMEOUT_MS, SEL_MATCH_STATS
from ..utils.browser import wait_for_cloudflare
from ..utils.log import get_logger

log = get_logger(__name__)


async def fetch_match_html(page: Page, url: str, match_id: int) -> str | None:
    """Navigate to a match page and return its HTML, or None on timeout/error.

    Cloudflare check happens here (after goto) so callers do not need to check
    before every request — avoiding an extra page.content() read per match.
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except Exception as e:
        log.warning("match_id=%d: page.goto failed (%s) — skipping", match_id, e)
        return None

    # handle Cloudflare challenge that may have intercepted this specific request
    await wait_for_cloudflare(page)

    # HLTV is server-side rendered — content is ready after domcontentloaded,
    # no need to wait for a specific selector (saves ~5s per match without stats)
    return await page.content()


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
