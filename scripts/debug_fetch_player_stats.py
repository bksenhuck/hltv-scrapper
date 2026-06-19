"""Fetches the HLTV player stats page and dumps the HTML + discovered filter options.

Usage:
    poetry run python scripts/debug_fetch_player_stats.py

Saves:
    data/debug_stats/player_stats_page.html  — raw page HTML
    data/debug_stats/player_filters.txt      — parsed filter options + table structure
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup

from src.hltv_scraper.conf.settings import STATS_PLAYERS_URL
from src.hltv_scraper.utils.browser import load_cookies, new_session, save_cookies, wait_for_cloudflare

FETCH_URL = f"{STATS_PLAYERS_URL}?rankingFilter=All"
DEBUG_STATS_DIR = Path("data/debug_stats")


async def main() -> None:
    DEBUG_STATS_DIR.mkdir(parents=True, exist_ok=True)

    async with new_session(headless=False) as browser:
        page = await browser.new_page()
        page.on("pageerror", lambda _: None)
        await load_cookies(page)

        print(f"Fetching: {FETCH_URL}")
        await page.goto(FETCH_URL, wait_until="domcontentloaded", timeout=30_000)
        await wait_for_cloudflare(page)

        await page.wait_for_timeout(3_000)

        html = await page.content()
        await save_cookies(page)

    html_path = DEBUG_STATS_DIR / "player_stats_page.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML saved: {html_path}  ({len(html):,} chars)")

    soup = BeautifulSoup(html, "html.parser")
    lines: list[str] = []

    lines.append("=" * 60)
    lines.append("SELECT ELEMENTS (dropdowns)")
    lines.append("=" * 60)
    for sel in soup.find_all("select"):
        name = sel.get("name") or sel.get("id") or sel.get("class") or "?"
        lines.append(f"\n<select name/id/class={name!r}>")
        for opt in sel.find_all("option"):
            val = opt.get("value", "")
            text = opt.get_text(strip=True)
            lines.append(f"  value={val!r:40s}  text={text!r}")

    lines.append("\n" + "=" * 60)
    lines.append("FILTER ANCHOR LINKS (href containing filter params)")
    lines.append("=" * 60)
    filter_keywords = ("rankingFilter", "startDate", "endDate", "maps", "matchType", "csVersion")
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(kw in href for kw in filter_keywords):
            if href not in seen:
                seen.add(href)
                lines.append(f"  {href}  |  text={a.get_text(strip=True)[:40]!r}")

    lines.append("\n" + "=" * 60)
    lines.append("STATS TABLE STRUCTURE")
    lines.append("=" * 60)
    table = soup.find("table")
    if table:
        lines.append(f"table classes: {table.get('class')}")
        thead = table.find("thead")
        if thead:
            headers = [th.get_text(strip=True) for th in thead.find_all(["th", "td"])]
            lines.append(f"headers: {headers}")
        tbody = table.find("tbody")
        if tbody:
            first_rows = tbody.find_all("tr")[:3]
            for i, tr in enumerate(first_rows):
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]
                lines.append(f"row[{i}]: {cells}")
                if i == 0:
                    lines.append(f"row[0] raw HTML:\n{tr}")
    else:
        lines.append("No <table> found.")

    filters_path = DEBUG_STATS_DIR / "player_filters.txt"
    filters_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Filters dump saved: {filters_path}")
    print("\nInspect data/debug_stats/player_filters.txt to verify column order.")


if __name__ == "__main__":
    asyncio.run(main())
