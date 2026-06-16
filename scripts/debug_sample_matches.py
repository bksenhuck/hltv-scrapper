"""Sample match HTMLs for debugging: most recent, oldest, and random matches per year.

Fetches results pages for the given year(s), selects a representative sample,
then downloads each match page and saves the HTML to data/debug_match/.

Usage:
    poetry run python scripts/debug_sample_matches.py              # all years (HLTV_START_YEAR → current)
    poetry run python scripts/debug_sample_matches.py --year 2024  # single year
    poetry run python scripts/debug_sample_matches.py --year 2024 --headless
"""
import argparse
import asyncio
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hltv_scraper.conf.settings import (
    DEBUG_MATCH_DIR,
    DEBUG_OLDEST_COUNT,
    DEBUG_RANDOM_COUNT,
    DEBUG_RECENT_COUNT,
    HLTV_START_YEAR,
    PAGE_SIZE,
    PAGE_TIMEOUT_MS,
)
from src.hltv_scraper.modules.results import fetch_page_html, parse_results, parse_total_pages
from src.hltv_scraper.utils.browser import load_cookies, new_session, save_cookies, wait_for_cloudflare
from src.hltv_scraper.utils.parsers import build_results_url, extract_match_id


async def _save_match_html(page, url: str, match_id: int, out_dir: Path) -> None:
    out = out_dir / f"{match_id}.html"
    if out.exists():
        print(f"    Skip (exists): {out.name}")
        return
    await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    await wait_for_cloudflare(page)
    html = await page.content()
    out.write_text(html, encoding="utf-8")
    print(f"    Saved: {out.name}  ({len(html):,} chars)")


async def _sample_year(page, year: int, out_dir: Path) -> None:
    print(f"\n[{year}] Fetching results…")

    html_p1 = await fetch_page_html(page, build_results_url(year=year, offset=0))
    if not html_p1:
        print(f"  Failed to fetch first results page for {year}")
        return

    total_pages = parse_total_pages(html_p1) or 1
    print(f"  {total_pages} page(s) found")

    matches_p1 = parse_results(html_p1)
    recent = matches_p1[:DEBUG_RECENT_COUNT]

    # Last page: oldest matches
    last_offset = (total_pages - 1) * PAGE_SIZE
    if last_offset > 0:
        html_last = await fetch_page_html(page, build_results_url(year=year, offset=last_offset))
        matches_last = parse_results(html_last) if html_last else []
    else:
        matches_last = matches_p1

    oldest = matches_last[-DEBUG_OLDEST_COUNT:]

    # Random middle page
    random_matches: list = []
    if total_pages > 2:
        mid_page = random.randint(1, total_pages - 2)
        html_mid = await fetch_page_html(
            page, build_results_url(year=year, offset=mid_page * PAGE_SIZE)
        )
        if html_mid:
            mid_matches = parse_results(html_mid)
            random_matches = random.sample(mid_matches, min(DEBUG_RANDOM_COUNT, len(mid_matches)))

    # Deduplicate by URL while preserving order
    seen: dict[str, object] = {}
    for m in recent + oldest + random_matches:
        if m.match_url and m.match_url not in seen:
            seen[m.match_url] = m

    print(f"  Fetching {len(seen)} unique match page(s)…")
    for url, match in seen.items():
        match_id = extract_match_id(url)
        if match_id is None:
            continue
        print(f"  [{match.date}] match_id={match_id}  {match.team1.name} vs {match.team2.name}")
        await _save_match_html(page, url, match_id, out_dir)


async def main(years: list[int], headless: bool) -> None:
    out_dir = Path(DEBUG_MATCH_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    async with new_session(headless=headless) as browser:
        page = await browser.new_page()
        page.on("pageerror", lambda _: None)
        await load_cookies(page)

        for year in years:
            await _sample_year(page, year, out_dir)

        await save_cookies(page)

    print(f"\nDone. HTML files saved to: {out_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download sample match HTML pages for debugging"
    )
    parser.add_argument(
        "--year", type=int, default=None,
        help=f"Year to sample (default: all years from {HLTV_START_YEAR} to current)",
    )
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode")
    args = parser.parse_args()

    if args.year is not None:
        years = [args.year]
    else:
        current_year = date.today().year
        years = list(range(HLTV_START_YEAR, current_year + 1))

    asyncio.run(main(years, args.headless))
