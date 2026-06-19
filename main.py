"""Entry point for HLTV match results scraper.

All logic lives in src/hltv_scraper/pipeline/results.py.

Usage:
  python main.py --year 2024 --no-headless
  python main.py --year-from 2012 --year-to 2026 --no-headless
  python main.py --year 2024 --parts maps stats
"""
import asyncio

from src.hltv_scraper.pipeline.results import main

if __name__ == "__main__":
    asyncio.run(main())
