"""Shared browser interaction and low-level HTML parse helpers used by all scraper modules."""
import asyncio

from bs4 import BeautifulSoup, Tag
from playwright.async_api import Page

from ..conf.settings import PAGE_TIMEOUT_MS, SEL_MATCH_STATS
from ..utils.browser import is_cloudflare_html
from ..utils.log import get_logger

log = get_logger(__name__)


async def fetch_match_html(page: Page, url: str, match_id: int) -> str | None:
    """Navigate to a match page and return its HTML, or None on error.

    page.content() is called exactly once per match — the same HTML is reused
    for the Cloudflare check, avoiding a second round-trip to the browser.
    """
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except Exception as e:
        log.warning("match_id=%d: page.goto failed (%s) — skipping", match_id, e)
        return None

    html = await page.content()

    if is_cloudflare_html(html):
        log.warning("match_id=%d: Cloudflare detected — waiting...", match_id)
        while True:
            await asyncio.sleep(2)
            html = await page.content()
            if not is_cloudflare_html(html):
                break
        log.info("match_id=%d: Cloudflare resolved", match_id)

    return html


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
