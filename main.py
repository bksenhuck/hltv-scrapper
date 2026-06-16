"""
HLTV scraper → data/datasets/{year}/{matches,maps,player_stats}.parquet

Default (no --parts): run_all — fetches each match page ONCE and saves all 3 files.
With --parts: run only the specified parts (matches / maps / stats).
  - 'maps' and 'stats' require matches.parquet to exist (provides the URLs).
  - Useful for reprocessing a single file without re-scraping everything.

Usage:
  python main.py --year 2024
  python main.py --year-from 2012 --year-to 2026
  python main.py --year 2024 --no-headless          # visible browser (Cloudflare)
  python main.py --year 2024 --debug                # verbose logs
  python main.py --year 2024 --force-download       # wipe + re-scrape selected parts
  python main.py --year 2024 --parts maps           # reprocess only maps.parquet
  python main.py --year 2024 --parts maps stats     # reprocess maps + player_stats
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
from src.hltv_scraper.modules.common import fetch_match_html
from src.hltv_scraper.modules.results import fetch_page_html, parse_results, parse_total_pages
from src.hltv_scraper.modules.scraper_maps import parse_map_rows
from src.hltv_scraper.modules.scraper_matches import parse_match_row
from src.hltv_scraper.modules.scraper_stats import parse_stat_rows
from src.hltv_scraper.utils.browser import load_cookies, new_session, save_cookies, wait_for_cloudflare
from src.hltv_scraper.utils.log import get_logger, setup_logging
from src.hltv_scraper.utils.parsers import build_results_url, extract_match_id
from src.hltv_scraper.utils.storage import (
    clear_maps, clear_matches, clear_player_stats, clear_year,
    load_match_records, load_saved_ids, load_saved_map_ids, load_saved_stat_ids,
    save_maps, save_matches, save_player_stats,
)

log = get_logger(__name__)


# ── helpers shared by all runners ─────────────────────────────────────────────

async def _iter_results_pages(page, year: int):
    """Yield (page_num, total_pages, match_results) for every results page of the year."""
    offset = 0
    total_pages: int | None = None
    while True:
        url = build_results_url(year=year, offset=offset)
        html = await fetch_page_html(page, url)
        if not html:
            break
        if offset == 0 and total_pages is None:
            total_pages = parse_total_pages(html)
            if total_pages:
                log.info("%d: ~%d page(s) detected", year, total_pages)
        matches = parse_results(html)
        if not matches:
            break
        page_num = offset // PAGE_SIZE + 1
        yield page_num, total_pages, matches
        offset += PAGE_SIZE


async def _fetch_and_save(page, match_id: int, url: str, year: int,
                          do_matches: bool, do_maps: bool, do_stats: bool,
                          match_result=None) -> bool:
    """Fetch one match page and save the requested parts. Returns True on success."""
    await wait_for_cloudflare(page)
    html = await fetch_match_html(page, url, match_id)
    if html is None:
        return False

    if do_matches and match_result is not None:
        save_matches([parse_match_row(html, match_result, match_id)], year)

    if do_maps:
        s1 = match_result.team1.score if match_result else 0
        s2 = match_result.team2.score if match_result else 0
        rows = parse_map_rows(html, match_id, s1, s2)
        if rows:
            save_maps(rows, year)

    if do_stats:
        rows = parse_stat_rows(html, match_id)
        if rows:
            save_player_stats(rows, year)

    return True


# ── run_all: single fetch per match, saves all 3 (default / most efficient) ───

async def run_all(page, year: int, force: bool) -> int:
    """Paginate results, fetch each match page once, save matches + maps + stats."""
    if force:
        clear_year(year)
    saved_ids = load_saved_ids(year)

    total_new = 0
    buffer_m: list[dict] = []
    buffer_mp: list[dict] = []
    buffer_st: list[dict] = []

    with tqdm(desc=f"{year} | pages", unit="page", leave=False) as page_bar:
        async for page_num, total_pages, match_results in _iter_results_pages(page, year):
            if total_pages and page_bar.total != total_pages:
                page_bar.total = total_pages
                page_bar.refresh()

            new_matches = [m for m in match_results
                           if extract_match_id(m.match_url or "") not in saved_ids]
            log.info(
                "Page %d/%s: %d matches | %d new | %d skipped",
                page_num, total_pages or "?",
                len(match_results), len(new_matches),
                len(match_results) - len(new_matches),
            )

            with tqdm(new_matches, desc=f"  {year} p{page_num}", unit="match", leave=False) as mbar:
                for match in mbar:
                    match_id = extract_match_id(match.match_url or "")
                    if not match_id:
                        continue
                    mbar.set_postfix({"id": match_id})

                    await wait_for_cloudflare(page)
                    html = await fetch_match_html(page, match.match_url, match_id)
                    if html is None:
                        continue

                    buffer_m.append(parse_match_row(html, match, match_id))
                    buffer_mp.extend(parse_map_rows(html, match_id, match.team1.score, match.team2.score))
                    buffer_st.extend(parse_stat_rows(html, match_id))

                    saved_ids.add(match_id)
                    total_new += 1

                    if total_new % SAVE_EVERY_N == 0:
                        save_matches(buffer_m, year)
                        save_maps(buffer_mp, year)
                        save_player_stats(buffer_st, year)
                        log.info("Checkpoint: %d new matches saved", total_new)
                        buffer_m.clear(); buffer_mp.clear(); buffer_st.clear()

                    await asyncio.sleep(MATCH_REQUEST_DELAY)

            page_bar.update(1)
            page_bar.set_postfix({"total_new": total_new})

    save_matches(buffer_m, year)
    save_maps(buffer_mp, year)
    save_player_stats(buffer_st, year)
    if buffer_m:
        log.info("Final flush: %d matches", len(buffer_m))
    return total_new


# ── run_matches: only matches.parquet ─────────────────────────────────────────

async def run_matches(page, year: int, force: bool) -> int:
    """Paginate results, fetch each match page, save only matches.parquet."""
    if force:
        clear_matches(year)
    saved_ids = load_saved_ids(year)

    total_new = 0
    buffer: list[dict] = []

    with tqdm(desc=f"{year} | pages", unit="page", leave=False) as page_bar:
        async for page_num, total_pages, match_results in _iter_results_pages(page, year):
            if total_pages and page_bar.total != total_pages:
                page_bar.total = total_pages
                page_bar.refresh()

            new_matches = [m for m in match_results
                           if extract_match_id(m.match_url or "") not in saved_ids]

            with tqdm(new_matches, desc=f"  {year} p{page_num}", unit="match", leave=False) as mbar:
                for match in mbar:
                    match_id = extract_match_id(match.match_url or "")
                    if not match_id:
                        continue
                    mbar.set_postfix({"id": match_id})

                    await wait_for_cloudflare(page)
                    html = await fetch_match_html(page, match.match_url, match_id)
                    if html is None:
                        continue

                    buffer.append(parse_match_row(html, match, match_id))
                    saved_ids.add(match_id)
                    total_new += 1

                    if total_new % SAVE_EVERY_N == 0:
                        save_matches(buffer, year)
                        log.info("Checkpoint: %d matches saved", total_new)
                        buffer.clear()

                    await asyncio.sleep(MATCH_REQUEST_DELAY)

            page_bar.update(1)

    save_matches(buffer, year)
    return total_new


# ── run_maps: only maps.parquet (requires matches.parquet) ────────────────────

async def run_maps(page, year: int, force: bool) -> int:
    """Load match URLs from matches.parquet, re-fetch pages, save only maps.parquet."""
    if force:
        clear_maps(year)
    saved_ids = load_saved_map_ids(year)
    records = [r for r in load_match_records(year) if r["match_id"] not in saved_ids]

    if not records:
        log.info("%d maps: nothing to process", year)
        return 0

    total_new = 0
    buffer: list[dict] = []

    with tqdm(records, desc=f"{year} maps", unit="match", leave=False) as mbar:
        for rec in mbar:
            match_id, url = rec["match_id"], rec["match_url"]
            mbar.set_postfix({"id": match_id})

            await wait_for_cloudflare(page)
            html = await fetch_match_html(page, url, match_id)
            if html is None:
                continue

            rows = parse_map_rows(html, match_id, rec["score_team1"], rec["score_team2"])
            buffer.extend(rows)
            total_new += 1

            if total_new % SAVE_EVERY_N == 0:
                save_maps(buffer, year)
                log.info("Checkpoint: %d matches processed (maps)", total_new)
                buffer.clear()

            await asyncio.sleep(MATCH_REQUEST_DELAY)

    save_maps(buffer, year)
    return total_new


# ── run_player_stats: only player_stats.parquet (requires matches.parquet) ────

async def run_player_stats(page, year: int, force: bool) -> int:
    """Load match URLs from matches.parquet, re-fetch pages, save only player_stats.parquet."""
    if force:
        clear_player_stats(year)
    saved_ids = load_saved_stat_ids(year)
    records = [r for r in load_match_records(year) if r["match_id"] not in saved_ids]

    if not records:
        log.info("%d stats: nothing to process", year)
        return 0

    total_new = 0
    buffer: list[dict] = []

    with tqdm(records, desc=f"{year} stats", unit="match", leave=False) as mbar:
        for rec in mbar:
            match_id, url = rec["match_id"], rec["match_url"]
            mbar.set_postfix({"id": match_id})

            await wait_for_cloudflare(page)
            html = await fetch_match_html(page, url, match_id)
            if html is None:
                continue

            rows = parse_stat_rows(html, match_id)
            buffer.extend(rows)
            total_new += 1

            if total_new % SAVE_EVERY_N == 0:
                save_player_stats(buffer, year)
                log.info("Checkpoint: %d matches processed (stats)", total_new)
                buffer.clear()

            await asyncio.sleep(MATCH_REQUEST_DELAY)

    save_player_stats(buffer, year)
    return total_new


# ── CLI ───────────────────────────────────────────────────────────────────────

async def main():
    parser = argparse.ArgumentParser(description=f"{SITE_NAME} results scraper")
    year_group = parser.add_mutually_exclusive_group(required=True)
    year_group.add_argument("--year", type=int, metavar="YEAR")
    year_group.add_argument("--year-from", type=int, metavar="YEAR")
    parser.add_argument("--year-to", type=int, metavar="YEAR")
    parser.add_argument("--no-headless", action="store_true",
                        help="Show the browser (required to resolve Cloudflare manually)")
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG level logs")
    parser.add_argument("--force-download", action="store_true",
                        help="Wipe existing data for selected parts and re-scrape from scratch")
    parser.add_argument("--parts", nargs="+", choices=["matches", "maps", "stats"],
                        metavar="PART",
                        help="Parts to run: matches / maps / stats (default: all via single-pass)")
    args = parser.parse_args()

    setup_logging(level=logging.DEBUG if args.debug else logging.INFO)

    if args.year:
        years = [args.year]
    elif args.year_from and args.year_to:
        years = list(range(args.year_from, args.year_to + 1))
    else:
        parser.error("--year-from requires --year-to")
        return

    parts = set(args.parts) if args.parts else None
    force = args.force_download

    log.info("Starting %s | Years: %s | Parts: %s", SITE_NAME, years, parts or "all")

    async with new_session(headless=not args.no_headless) as browser:
        browser_page = await browser.new_page()
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

                    if parts is None:
                        n = await run_all(browser_page, year, force)
                        log.info("%d done: %d new matches", year, n)
                    else:
                        if "matches" in parts:
                            n = await run_matches(browser_page, year, force)
                            log.info("%d matches done: %d new", year, n)
                        if "maps" in parts:
                            n = await run_maps(browser_page, year, force)
                            log.info("%d maps done: %d matches processed", year, n)
                        if "stats" in parts:
                            n = await run_player_stats(browser_page, year, force)
                            log.info("%d stats done: %d matches processed", year, n)
        finally:
            await save_cookies(browser_page)

    log.info("Scraping complete. Data in: %s/", DATA_DIR)


if __name__ == "__main__":
    asyncio.run(main())
