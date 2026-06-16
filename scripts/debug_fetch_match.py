"""Saves the HTML of a specific match page for selector inspection.

Usage:
    poetry run python scripts/debug_fetch_match.py <match_id_or_url>

Examples:
    poetry run python scripts/debug_fetch_match.py 1973537
    poetry run python scripts/debug_fetch_match.py 2209322
    poetry run python scripts/debug_fetch_match.py https://www.hltv.org/matches/1973537/darkpassage-vs-rth-...
"""
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hltv_scraper.conf.settings import DEBUG_MATCH_DIR, HLTV_BASE_URL
from src.hltv_scraper.utils.browser import load_cookies, new_session, save_cookies, wait_for_cloudflare


def _resolve(arg: str) -> tuple[str, int]:
    """Return (url, match_id) from either a full URL or a bare match ID."""
    if arg.startswith("http"):
        match = re.search(r"/matches/(\d+)/", arg)
        if not match:
            raise ValueError(f"Could not extract match_id from URL: {arg}")
        return arg, int(match.group(1))
    match_id = int(arg)
    return f"{HLTV_BASE_URL}/matches/{match_id}/match", match_id


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url, match_id = _resolve(sys.argv[1])
    out_dir = Path(DEBUG_MATCH_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{match_id}.html"

    async with new_session(headless=False) as browser:
        page = await browser.new_page()
        page.on("pageerror", lambda _: None)
        await load_cookies(page)

        print(f"Fetching: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await wait_for_cloudflare(page)

        html = await page.content()
        out.write_text(html, encoding="utf-8")
        await save_cookies(page)

    print(f"Saved: {out}  ({len(html):,} chars)")


if __name__ == "__main__":
    asyncio.run(main())
