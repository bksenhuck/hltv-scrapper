import math
import re
from datetime import date, datetime
from urllib.parse import urlencode

from bs4 import BeautifulSoup

from ..conf.settings import PAGE_SIZE, RESULTS_URL, SEL_PAGINATION_DATA


def parse_date(text: str) -> date:
    """Convert 'Results for June 14th 2025' to a date object."""
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", text)
    cleaned = cleaned.replace("Results for ", "").strip()
    return datetime.strptime(cleaned, "%B %d %Y").date()


def build_results_url(year: int | None = None, offset: int = 0) -> str:
    """Build the results URL with optional year filter and pagination offset."""
    params: dict[str, str] = {}
    if year is not None:
        params["startDate"] = f"{year}-01-01"
        params["endDate"] = f"{year}-12-31"
    if offset > 0:
        params["offset"] = str(offset)
    return f"{RESULTS_URL}?{urlencode(params)}" if params else RESULTS_URL


def extract_match_id(url: str) -> int | None:
    """Extract the numeric match_id from a URL like /matches/2200750/mouz-vs-..."""
    match = re.search(r"/matches/(\d+)/", url)
    return int(match.group(1)) if match else None


def parse_total_pages(html: str) -> int | None:
    """Read .pagination-data to determine the total number of pages for the year.

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
