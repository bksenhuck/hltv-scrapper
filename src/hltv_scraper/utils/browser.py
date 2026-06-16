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


async def _is_cloudflare(page: Page) -> bool:
    try:
        title = (await page.title()).lower()
        snippet = (await page.content())[:3000].lower()
        return any(m in title or m in snippet for m in _CLOUDFLARE_MARKERS)
    except Exception:
        return False


async def wait_for_cloudflare(page: Page) -> None:
    """Block until the Cloudflare challenge disappears."""
    while await _is_cloudflare(page):
        log.warning(
            "Cloudflare detected!\n"
            "  1. In the open browser, click 'Verify you are human' / checkbox\n"
            "  2. Wait for HLTV to load\n"
            "  3. Then press Enter here"
        )
        try:
            input("\n  [WAITING] Press Enter after HLTV loads in the browser... ")
        except EOFError:
            return

        await asyncio.sleep(2)

        if await _is_cloudflare(page):
            log.warning("Challenge still active — repeat the process in the browser.")
        else:
            log.info("Cloudflare resolved!")
