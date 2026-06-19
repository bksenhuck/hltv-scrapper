"""Fetches the HLTV team stats page and dumps the HTML + discovered filter options.

Usage:
    poetry run python scripts/debug_fetch_team_stats.py

Saves:
    data/debug_stats/team_stats_page.html  — raw page HTML
    data/debug_stats/filters.txt           — parsed filter options (select elements + their values)
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup

from src.hltv_scraper.conf.settings import HLTV_BASE_URL
from src.hltv_scraper.utils.browser import load_cookies, new_session, save_cookies, wait_for_cloudflare

STATS_TEAMS_URL = f"{HLTV_BASE_URL}/stats/teams?rankingFilter=All"
DEBUG_STATS_DIR = Path("data/debug_stats")


async def main() -> None:
    DEBUG_STATS_DIR.mkdir(parents=True, exist_ok=True)

    async with new_session(headless=False) as browser:
        page = await browser.new_page()
        page.on("pageerror", lambda _: None)
        await load_cookies(page)

        print(f"Fetching: {STATS_TEAMS_URL}")
        await page.goto(STATS_TEAMS_URL, wait_until="domcontentloaded", timeout=30_000)
        await wait_for_cloudflare(page)

        # wait a bit for JS-rendered dropdowns to populate
        await page.wait_for_timeout(3_000)

        html = await page.content()
        await save_cookies(page)

    # save raw HTML
    html_path = DEBUG_STATS_DIR / "team_stats_page.html"
    html_path.write_text(html, encoding="utf-8")
    print(f"HTML saved: {html_path}  ({len(html):,} chars)")

    # parse and dump filter options
    soup = BeautifulSoup(html, "html.parser")
    lines: list[str] = []

    # --- select elements (dropdowns) ---
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

    # --- look for filter-related links / data attributes ---
    lines.append("\n" + "=" * 60)
    lines.append("FILTER-RELATED ELEMENTS (data-*, filter classes, etc.)")
    lines.append("=" * 60)
    for el in soup.find_all(attrs={"data-filter": True}):
        lines.append(f"tag={el.name} data-filter={el.get('data-filter')!r} classes={el.get('class')}")
    for el in soup.find_all(class_=lambda c: c and "filter" in " ".join(c).lower()):
        lines.append(f"tag={el.name} class={el.get('class')} text={el.get_text(strip=True)[:80]!r}")

    # --- look for <a> tags that look like filter links ---
    lines.append("\n" + "=" * 60)
    lines.append("FILTER ANCHOR LINKS (href containing filter params)")
    lines.append("=" * 60)
    filter_keywords = ("rankingFilter", "startDate", "endDate", "maps", "event", "game", "matchType")
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if any(kw in href for kw in filter_keywords):
            if href not in seen:
                seen.add(href)
                lines.append(f"  {href}  |  text={a.get_text(strip=True)[:40]!r}")

    # --- look for the stats table ---
    lines.append("\n" + "=" * 60)
    lines.append("STATS TABLE STRUCTURE (first table)")
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
                # show raw HTML of first row
                if i == 0:
                    lines.append(f"row[0] raw HTML:\n{tr}")
    else:
        lines.append("No <table> found.")

    # --- look for div-based filter UI ---
    lines.append("\n" + "=" * 60)
    lines.append("DIV-BASED FILTER UI (possible JS dropdowns)")
    lines.append("=" * 60)
    for div in soup.find_all("div", class_=True):
        classes = " ".join(div.get("class", []))
        if any(kw in classes.lower() for kw in ("filter", "dropdown", "select", "picker")):
            lines.append(f"\ndiv.{classes}:")
            lines.append(f"  {div.get_text(' ', strip=True)[:200]!r}")
            # show child <a> or <span> options
            for child in div.find_all(["a", "li", "span"], limit=20):
                v = child.get("data-value") or child.get("value") or child.get("href") or ""
                t = child.get_text(strip=True)
                if t:
                    lines.append(f"    {child.name} value={v!r} text={t!r}")

    # --- look for any JSON data embedded in the page ---
    lines.append("\n" + "=" * 60)
    lines.append("EMBEDDED JSON / script data")
    lines.append("=" * 60)
    for script in soup.find_all("script"):
        src = script.get("src", "")
        text = script.string or ""
        if any(kw in text for kw in ("filter", "event", "maps", "rankingFilter")):
            snippet = text[:500].replace("\n", " ")
            lines.append(f"<script src={src!r}>: {snippet!r}")

    filters_path = DEBUG_STATS_DIR / "filters.txt"
    filters_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Filters dump saved: {filters_path}")
    print("\nNext step: inspect data/debug_stats/filters.txt and data/debug_stats/team_stats_page.html")


if __name__ == "__main__":
    asyncio.run(main())
