import asyncio
import functools
import logging
import time
from collections.abc import Callable

_FORMAT = "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s"
_DATE = "%H:%M:%S"


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(format=_FORMAT, datefmt=_DATE, level=level, force=True)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_call(func: Callable) -> Callable:
    """Decorator that logs module + function name on every call (sync and async) at DEBUG level."""
    logger = logging.getLogger(func.__module__)
    qualname = func.__qualname__

    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def _async(*args, **kwargs):
            logger.debug("→ %s()", qualname)
            t0 = time.perf_counter()
            result = await func(*args, **kwargs)
            logger.debug("← %s()  [%.2fs]", qualname, time.perf_counter() - t0)
            return result
        return _async

    @functools.wraps(func)
    def _sync(*args, **kwargs):
        logger.debug("→ %s()", qualname)
        t0 = time.perf_counter()
        result = func(*args, **kwargs)
        logger.debug("← %s()  [%.2fs]", qualname, time.perf_counter() - t0)
        return result
    return _sync
