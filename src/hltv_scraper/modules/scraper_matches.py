"""Parse match-level info (team names, scores, event, stage, format) from a match page HTML."""
import re

from bs4 import BeautifulSoup

from ..conf.settings import (
    SEL_MATCH_DATE,
    SEL_MATCH_EVENT,
    SEL_MATCH_FORMAT,
    SEL_MATCH_STAGE,
    SEL_MATCH_TIME,
)
from ..models import MatchResult


def parse_match_row(html: str, match: MatchResult, match_id: int) -> dict:
    """Return a dict ready for matches.parquet from the match page HTML + results-page data."""
    soup = BeautifulSoup(html, "html.parser")
    match_time = _text(soup, SEL_MATCH_DATE) or _text(soup, SEL_MATCH_TIME)
    event = _text(soup, SEL_MATCH_EVENT) or match.event
    return {
        "match_id":    match_id,
        "date":        match.date.isoformat(),
        "year":        match.date.year,
        "month":       match.date.month,
        "match_time":  match_time,
        "team1":       match.team1.name,
        "team2":       match.team2.name,
        "score_team1": match.team1.score,
        "score_team2": match.team2.score,
        "event":       event,
        "stage":       _parse_stage(soup),
        "format":      _parse_format(soup),
        "match_url":   match.match_url,
    }


def _text(soup: BeautifulSoup, selector: str) -> str | None:
    el = soup.select_one(selector)
    return el.get_text(strip=True) or None if el else None


def _parse_stage(soup: BeautifulSoup) -> str | None:
    el = soup.select_one(SEL_MATCH_STAGE)
    if el:
        return el.get_text(strip=True) or None
    banner = soup.select_one(".timeAndEvent")
    if banner:
        text = banner.get_text(" ", strip=True)
        m = re.search(r"(Quarter|Semi|Grand\s*Final|Final|Group\s*Stage|Play[- ]?[Oo]ff)", text)
        if m:
            return m.group(0)
    return None


def _parse_format(soup: BeautifulSoup) -> str | None:
    el = soup.select_one(SEL_MATCH_FORMAT)
    if el:
        text = el.get_text(" ", strip=True)
        m = re.search(r"[Bb]est\s+of\s+(\d)", text)
        if m:
            return f"bo{m.group(1)}"
    text = soup.get_text(" ", strip=True)
    m = re.search(r"[Bb]est\s+of\s+(\d)", text)
    return f"bo{m.group(1)}" if m else None
