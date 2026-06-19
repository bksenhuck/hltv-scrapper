"""Pipeline for scraping /stats/teams across all filter combinations.

Resumes automatically via progress.json. Output partitioned by year:
  data/datasets/team_stats/{year}/team_stats.parquet
"""
import asyncio
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

import polars as pl

from ..conf.settings import (
    MATCH_REQUEST_DELAY_MAX,
    MATCH_REQUEST_DELAY_MIN,
    PAGE_TIMEOUT_MS,
    STATS_SAVE_EVERY,
    STATS_TEAMS_DATA_DIR,
    STATS_TEAMS_PARQUET,
    STATS_TEAMS_PROGRESS,
)
from ..modules.stats.teams import (
    build_team_stats_url,
    combo_key,
    get_all_combinations,
    parse_team_stats_table,
)
from ..utils.browser import is_cloudflare_html, load_cookies, new_session, save_cookies
from ..utils.log import get_logger, setup_logging

log = get_logger(__name__)

_OUT_DIR    = Path(STATS_TEAMS_DATA_DIR)
_PROGRESS_F = _OUT_DIR / STATS_TEAMS_PROGRESS


def _year_parquet(year) -> Path:
    folder = _OUT_DIR / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    return folder / STATS_TEAMS_PARQUET


def _load_progress() -> set[str]:
    if _PROGRESS_F.exists():
        return set(json.loads(_PROGRESS_F.read_text(encoding="utf-8")))
    return set()


def _save_progress(done: set[str]) -> None:
    _PROGRESS_F.write_text(json.dumps(sorted(done)), encoding="utf-8")


def _flush(buffer: list[dict], done: set[str]) -> None:
    if not buffer:
        _save_progress(done)
        return

    by_year: dict[str, list[dict]] = defaultdict(list)
    for row in buffer:
        by_year[row["year"]].append(row)

    total_written = 0
    for year_val, rows in by_year.items():
        path = _year_parquet(year_val)
        new_df = pl.DataFrame(rows)
        if path.exists():
            existing = pl.read_parquet(path)
            df = pl.concat([existing, new_df], how="diagonal_relaxed")
        else:
            df = new_df
        df.write_parquet(path)
        total_written += len(rows)
        log.info("  -> %s  (%d rows, total %d)", path, len(rows), len(df))

    _save_progress(done)
    log.info("Flushed %d rows across %d year folder(s). %d combos done.",
             total_written, len(by_year), len(done))


async def _fetch_html(page, url: str) -> str | None:
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
    except Exception as e:
        log.warning("page.goto failed: %s", e)
        return None

    html = await page.content()

    if is_cloudflare_html(html):
        log.warning("Cloudflare detected — waiting...")
        while True:
            await asyncio.sleep(2)
            html = await page.content()
            if not is_cloudflare_html(html):
                break
        log.info("Cloudflare resolved")

    return html


async def main() -> None:
    setup_logging()
    headless = "--no-headless" not in sys.argv
    _OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_combos = get_all_combinations()
    log.info("Total combinations: %d", len(all_combos))

    done = _load_progress()
    remaining = [c for c in all_combos if combo_key(*c) not in done]
    log.info("Already done: %d  |  Remaining: %d", len(done), len(remaining))

    if not remaining:
        log.info("Nothing to do — all combinations already scraped.")
        return

    buffer: list[dict] = []

    async with new_session(headless=headless) as browser:
        page = await browser.new_page()
        page.on("pageerror", lambda _: None)
        await load_cookies(page)

        for i, (year, match_type, map_name, cs_version) in enumerate(remaining):
            url = build_team_stats_url(year, match_type, map_name, cs_version)
            log.info(
                "[%d/%d] year=%-4s  type=%-10s  map=%-14s  ver=%s",
                i + 1, len(remaining),
                year, match_type or "all", map_name or "all", cs_version or "both",
            )

            html = await _fetch_html(page, url)
            if html:
                rows = parse_team_stats_table(html, year, match_type, map_name, cs_version)
                buffer.extend(rows)

            done.add(combo_key(year, match_type, map_name, cs_version))

            if (i + 1) % STATS_SAVE_EVERY == 0:
                log.info("--- checkpoint %d/%d ---", i + 1, len(remaining))
                _flush(buffer, done)
                buffer.clear()

            await page.wait_for_timeout(
                int(random.uniform(MATCH_REQUEST_DELAY_MIN, MATCH_REQUEST_DELAY_MAX) * 1000)
            )

        await save_cookies(page)

    _flush(buffer, done)
    log.info("Scrape complete. %d combinations processed.", len(remaining))
