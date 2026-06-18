"""
Browser session using camoufox.

IMPORTANT: do not override user_agent, viewport, or locale via new_context() —
camoufox configures all of these internally to mimic a real browser.
Any override breaks the fingerprint and lets Cloudflare detect automation.
"""
import asyncio
import json
from pathlib import Path

from playwright.async_api import Page

from ..conf.settings import BROWSER_HEADLESS, COOKIES_FILE
from .log import get_logger

log = get_logger(__name__)

_CLOUDFLARE_MARKERS = (
    "just a moment",
    "cf-challenge",
    "challenge-running",
    "verify you are human",
    "ddos protection by cloudflare",
)


def new_session(headless: bool = BROWSER_HEADLESS):
    """Return the AsyncCamoufox context manager. Use as: async with new_session() as browser."""
    from camoufox.async_api import AsyncCamoufox
    return AsyncCamoufox(
        headless=headless,
        geoip=True,
        os=("windows",),
        # do NOT pass user_agent, viewport, locale — camoufox handles them
    )


async def load_cookies(page: Page) -> None:
    path = Path(COOKIES_FILE)
    if path.exists():
        cookies = json.loads(path.read_text(encoding="utf-8"))
        await page.context.add_cookies(cookies)
        log.debug("Cookies loaded: %s (%d)", COOKIES_FILE, len(cookies))
    else:
        log.debug("No saved cookies found")


async def save_cookies(page: Page) -> None:
    cookies = await page.context.cookies()
    Path(COOKIES_FILE).write_text(json.dumps(cookies, indent=2), encoding="utf-8")
    log.debug("Cookies saved: %s (%d)", COOKIES_FILE, len(cookies))


def is_cloudflare_html(html: str) -> bool:
    """Check a pre-fetched HTML string for Cloudflare challenge markers."""
    snippet = html[:3000].lower()
    return any(m in snippet for m in _CLOUDFLARE_MARKERS)


async def wait_for_cloudflare(page: Page) -> None:
    """Used only for the initial HLTV page load. Polls until challenge disappears."""
    try:
        title = (await page.title()).lower()
        html  = await page.content()
    except Exception:
        return
    if not (any(m in title for m in _CLOUDFLARE_MARKERS) or is_cloudflare_html(html)):
        return
    log.warning("Cloudflare challenge detected — waiting for it to resolve in the browser...")
    while True:
        await asyncio.sleep(2)
        try:
            html = await page.content()
        except Exception:
            return
        if not is_cloudflare_html(html):
            break
    log.info("Cloudflare resolved!")
