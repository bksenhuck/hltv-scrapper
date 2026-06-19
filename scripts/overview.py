"""Entry point for HLTV dataset completeness check.

All logic lives in src/hltv_scraper/pipeline/overview.py.

Usage:
  poetry run python scripts/overview.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hltv_scraper.pipeline.overview import main

if __name__ == "__main__":
    main()
