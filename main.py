"""
HLTV scraper → data/datasets/{year}/{month:02d}.parquet

Flow:
  For each year:
    For each results page (automatic pagination):
      For each match on the page:
        - Opens the individual match page
        - Extracts maps + player stats
        - Saves incrementally every SAVE_EVERY_N matches

Auto-resume: matches already saved in Parquet are skipped.

Usage:
  python main.py --year 2024
  python main.py --year-from 2012 --year-to 2024
  python main.py --year 2024 --no-headless    # visible browser (Cloudflare)
  python main.py --year 2024 --debug          # DEBUG logs
"""
import argparse
import asyncio
import logging
from pathlib import Path

from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from src.hltv_scraper.conf.settings import (
    DATA_DIR, MATCH_REQUEST_DELAY, PAGE_SIZE, SAVE_EVERY_N, SITE_NAME,
)
from src.hltv_scraper.models import MatchDetail
from src.hltv_scraper.modules.match import scrape_match_detail
from src.hltv_scraper.modules.results import fetch_page_html, parse_results, parse_total_pages
from src.hltv_scraper.utils.browser import load_cookies, new_session, save_cookies, wait_for_cloudflare
from src.hltv_scraper.utils.log import get_logger, setup_logging
from src.hltv_scraper.utils.parsers import build_results_url, extract_match_id
from src.hltv_scraper.utils.storage import append_to_parquet, load_saved_ids

log = get_logger(__name__)


async def _scrape_year(page, year: int) -> int:
    """
    Iterate all results pages for the year and, for each match,
    open the individual page and extract full details.

    Auto-resumes — matches already in Parquet are skipped.
    Saves every SAVE_EVERY_N matches to avoid losing progress.

    Returns the total number of newly collected matches.
    """
    saved_ids = load_saved_ids(year)
    log.info("%d: %d matches already saved (resuming)", year, len(saved_ids))

    buffer: list[MatchDetail] = []
    total_new = 0
    total_pages: int | None = None
    offset = 0

    with tqdm(desc=f"{year} | pages", unit="page", leave=False) as page_bar:
        while True:
            url = build_results_url(year=year, offset=offset)
            html = await fetch_page_html(page, url)
            if not html:
                break

            # detect total pages on the first request
            if offset == 0 and total_pages is None:
                total_pages = parse_total_pages(html)
                if total_pages:
                    page_bar.total = total_pages
                    page_bar.refresh()
                    log.info("%d: ~%d page(s) detected", year, total_pages)

            match_results = parse_results(html)
            if not match_results:
                break

            page_num = offset // PAGE_SIZE + 1
            new_on_page = [m for m in match_results
                           if extract_match_id(m.match_url or "") not in saved_ids]

            log.info(
                "Page %d/%s: %d matches | %d new | %d already saved",
                page_num, str(total_pages) if total_pages else "?",
                len(match_results), len(new_on_page),
                len(match_results) - len(new_on_page),
            )

            with tqdm(new_on_page, desc=f"  {year} p{page_num}", unit="match", leave=False) as match_bar:
                for match in match_bar:
                    match_id = extract_match_id(match.match_url or "")
                    if not match_id:
                        continue

                    match_bar.set_postfix({"id": match_id, "teams": f"{match.team1.name} vs {match.team2.name}"})

                    await wait_for_cloudflare(page)

                    detail = await scrape_match_detail(page, match)
                    if not detail:
                        continue

                    buffer.append(detail)
                    saved_ids.add(match_id)
                    total_new += 1

                    if len(buffer) >= SAVE_EVERY_N:
                        append_to_parquet(buffer, year)
                        log.info("Checkpoint: %d matches saved (total new: %d)", len(buffer), total_new)
                        buffer.clear()

                    await asyncio.sleep(MATCH_REQUEST_DELAY)

            offset += PAGE_SIZE
            page_bar.update(1)
            page_bar.set_postfix({"total_new": total_new})

    if buffer:
        append_to_parquet(buffer, year)
        log.info("Final flush: %d matches saved", len(buffer))

    return total_new


async def main():
    parser = argparse.ArgumentParser(description=f"{SITE_NAME} results scraper")
    year_group = parser.add_mutually_exclusive_group(required=True)
    year_group.add_argument("--year", type=int, metavar="YEAR", help="Single year (e.g. 2024)")
    year_group.add_argument("--year-from", type=int, metavar="YEAR", help="Start of year range")
    parser.add_argument("--year-to", type=int, metavar="YEAR", help="End of year range (requires --year-from)")
    parser.add_argument("--no-headless", action="store_true",
                        help="Show the browser — required to resolve Cloudflare manually")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG level logs")
    args = parser.parse_args()

    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)

    if args.year:
        years = [args.year]
    elif args.year_from and args.year_to:
        years = list(range(args.year_from, args.year_to + 1))
    else:
        parser.error("--year-from requires --year-to")
        return

    log.info("Starting %s | Years: %s", SITE_NAME, years)

    async with new_session(headless=not args.no_headless) as browser:
        browser_page = await browser.new_page()
        # suppress JS page errors (e.g. old 2012 pages without location info)
        # without this the Firefox driver crashes in the pageerror handler
        browser_page.on("pageerror", lambda _: None)
        await load_cookies(browser_page)

        log.info("Opening HLTV...")
        await browser_page.goto("https://www.hltv.org", wait_until="domcontentloaded", timeout=30_000)
        await wait_for_cloudflare(browser_page)
        await save_cookies(browser_page)

        try:
            with logging_redirect_tqdm():
                for year in tqdm(years, desc="Years", unit="year"):
                    log.info("=== %d ===", year)
                    n = await _scrape_year(browser_page, year)
                    log.info("%d done: %d new matches collected", year, n)
        finally:
            await save_cookies(browser_page)

    log.info("Scraping complete. Data in: %s/", DATA_DIR)


if __name__ == "__main__":
    asyncio.run(main())
