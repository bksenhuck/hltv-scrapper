import math
import re
from datetime import date

from bs4 import BeautifulSoup
from playwright.async_api import Page, async_playwright

from ..conf.settings import (
    BROWSER_HEADLESS,
    HLTV_BASE_URL,
    PAGE_SIZE,
    PAGE_TIMEOUT_MS,
    SEL_DATE_HEADING,
    SEL_EVENT,
    SEL_PAGINATION_DATA,
    SEL_RESULT_ROW,
    SEL_RESULTS_HOLDER,
    SEL_RESULTS_SUBLIST,
    SEL_SCORE,
    SEL_TEAM,
    SELECTOR_TIMEOUT_MS,
    USER_AGENT,
)
from ..models import MatchResult, TeamResult
from ..utils.browser import wait_for_cloudflare
from ..utils.log import get_logger, log_call
from ..utils.parsers import build_results_url, parse_date

log = get_logger(__name__)


_RESULT_SELECTORS = [
    SEL_RESULTS_HOLDER,    # .results-all
    SEL_RESULTS_SUBLIST,   # .results-sublist
    ".result-con",
    ".results-holder",
    ".allresults",
]

_CONSENT_SELECTORS = [
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "button[id*='accept']",
    "button[id*='consent']",
    ".accept-button",
]


@log_call
async def fetch_page_html(page: Page, url: str, debug_dump: bool = False) -> str | None:
    """
    Load the URL, dismiss any consent banner, and wait for results content.
    Saves debug_page.html on failure for inspection.
    """
    log.info("Fetching: %s", url)
    await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    await wait_for_cloudflare(page)

    # dismiss cookie/consent banner if present
    for sel in _CONSENT_SELECTORS:
        try:
            btn = await page.query_selector(sel)
            if btn:
                await btn.click()
                log.debug("Consent banner dismissed (%s)", sel)
                await page.wait_for_timeout(1_000)
                break
        except Exception:
            pass

    # try each results selector
    for selector in _RESULT_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=5_000)
            log.debug("Selector found: %s", selector)
            return await page.content()
        except Exception:
            log.debug("Selector not found: %s", selector)

    # last resort: check for known strings in the raw HTML
    try:
        html = await page.content()
    except Exception as e:
        log.error("Failed to get page content (%s). Browser closed?", e)
        return None

    if any(kw in html for kw in ("result-con", "results-sublist", "results-holder")):
        log.debug("Results content detected via string search")
        return html

    # save HTML for diagnosis
    from pathlib import Path
    dump = Path("debug_page.html")
    dump.write_text(html, encoding="utf-8")
    log.warning("No results selector found. HTML saved to: %s", dump)
    return None


def parse_total_pages(html: str) -> int | None:
    """
    Read .pagination-data to determine the total number of pages for the year.
    Expected text formats: '1-100 of 3847' or data-total='3847'.
    """
    soup = BeautifulSoup(html, "html.parser")
    el = soup.select_one(SEL_PAGINATION_DATA)
    if not el:
        return None

    raw = el.get("data-total") or el.get("data-pages")
    if raw:
        try:
            return math.ceil(int(raw) / PAGE_SIZE)
        except ValueError:
            pass

    text = el.get_text(strip=True)
    m = re.search(r"of\s+([\d,]+)", text, re.IGNORECASE)
    if m:
        total = int(m.group(1).replace(",", ""))
        return math.ceil(total / PAGE_SIZE)

    m = re.search(r"([\d,]+)", text)
    if m:
        total = int(m.group(1).replace(",", ""))
        return math.ceil(total / PAGE_SIZE)

    return None


@log_call
def parse_results(html: str) -> list[MatchResult]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[MatchResult] = []

    for sublist in soup.select(SEL_RESULTS_SUBLIST):
        date_heading = sublist.select_one(SEL_DATE_HEADING)
        if not date_heading:
            continue
        match_date = parse_date(date_heading.get_text(strip=True))
        for row in sublist.select(SEL_RESULT_ROW):
            match = _parse_row(row, match_date)
            if match:
                results.append(match)

    log.debug("parse_results: %d matches extracted", len(results))
    return results


def _parse_row(row, match_date: date) -> MatchResult | None:
    try:
        teams = row.select(SEL_TEAM)
        scores = row.select(SEL_SCORE)
        event_el = row.select_one(SEL_EVENT)
        href = row.get("href", "")

        if len(teams) < 2 or len(scores) < 2:
            return None

        return MatchResult(
            date=match_date,
            team1=TeamResult(name=teams[0].get_text(strip=True), score=int(scores[0].get_text(strip=True))),
            team2=TeamResult(name=teams[1].get_text(strip=True), score=int(scores[1].get_text(strip=True))),
            event=event_el.get_text(strip=True) if event_el else "",
            match_url=f"{HLTV_BASE_URL}{href}" if href else None,
        )
    except (ValueError, IndexError):
        return None


async def scrape_results(
    year: int | None = None,
    headless: bool = BROWSER_HEADLESS,
    max_pages: int | None = None,
) -> list[MatchResult]:
    """Standalone convenience function that opens and closes the browser internally."""
    all_results: list[MatchResult] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(user_agent=USER_AGENT)
        page = await context.new_page()

        try:
            page_num = 0
            while True:
                if max_pages is not None and page_num >= max_pages:
                    break
                url = build_results_url(year=year, offset=page_num * PAGE_SIZE)
                html = await fetch_page_html(page, url)
                if not html:
                    break
                page_results = parse_results(html)
                if not page_results:
                    break
                all_results.extend(page_results)
                page_num += 1
        finally:
            await browser.close()

    return all_results
