"""Entry point for HLTV team stats scraper.

All logic lives in src/hltv_scraper/pipeline/team_stats.py.

Usage:
  poetry run python scripts/scrape_team_stats.py --no-headless
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hltv_scraper.pipeline.team_stats import main

if __name__ == "__main__":
    asyncio.run(main())
