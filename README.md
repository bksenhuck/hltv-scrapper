# HLTV Scraper

Scrapes three datasets from [HLTV.org](https://www.hltv.org) and saves them as Parquet files partitioned by year:

| Dataset | Source | Rows (all years) |
|---|---|---|
| Match results | `/results` + individual match pages | varies by year |
| Team stats | `/stats/teams` | ~50k |
| Player stats | `/stats/players` | ~430k |

All scrapers use [camoufox](https://github.com/daijro/camoufox) (anti-detect Firefox via Playwright) and handle Cloudflare automatically. Progress is checkpointed so interrupted runs resume where they left off.

---

## Installation

```bash
poetry install
poetry run camoufox fetch   # download the patched Firefox binary
```

---

## Match results scraper

Runs a 3-level loop: results pages → match URLs → individual match pages.

```
For each YEAR
  └── For each results PAGE (offset 0, 100, 200 … until exhausted)
        └── For each MATCH on the page
              └── Opens the individual match URL
                    → parses match header, maps, and player stats
                    → checkpoints to Parquet every N matches
```

**Usage:**

```bash
# scrape a single year
poetry run python main.py --year 2024 --no-headless

# scrape a range of years
poetry run python main.py --year-from 2012 --year-to 2026 --no-headless

# reprocess only one part without re-scraping
poetry run python main.py --year 2024 --parts maps
poetry run python main.py --year 2024 --parts stats
poetry run python main.py --year 2024 --parts maps stats

# wipe and re-scrape from scratch
poetry run python main.py --year 2024 --force-download --no-headless
```

> Always use `--no-headless`. In headless mode Cloudflare blocks the browser and the scraper waits indefinitely.

**Output — `data/datasets/results/{year}/`:**

| File | Schema |
|---|---|
| `matches.parquet` | `match_id`, `date`, `year`, `month`, `match_time`, `team1`, `team2`, `score_team1`, `score_team2`, `event`, `stage`, `format`, `match_url` |
| `maps.parquet` | `match_id`, `map_order`, `map_name`, `score_team1`, `score_team2` |
| `player_stats.parquet` | `match_id`, `map_order`, `team`, `side`, `player_name`, `kills`, `deaths`, `adr`, `kast`, `rating` |

`map_order=0` is the "All Maps" aggregate; `map_order=1+` are individual maps in play order.  
`side` is one of `"both"` / `"ct"` / `"t"`.

---

## Team stats scraper

Scrapes `/stats/teams` across every combination of year × match type × map × CS version.

**Dimensions — 4 032 total combinations:**

| Dimension | Values |
|---|---|
| year | `all` + 2012–2026 (16 values) |
| match_type | `all`, `Majors`, `BigEvents`, `MvpEvents`, `Lan`, `Online` |
| map | `all` + 13 maps |
| cs_version | `both`, `CS2`, `CSGO` |

**Usage:**

```bash
poetry run python scripts/scrape_team_stats.py --no-headless
```

**Output — `data/datasets/team_stats/{year}/team_stats.parquet`:**

`year`, `match_type`, `map_name`, `cs_version`, `rank`, `team_id`, `team_name`, `country`, `maps_played`, `kd_diff`, `kd_ratio`, `rating`, `scraped_at`

---

## Player stats scraper

Scrapes `/stats/players` across the same 4 032 combinations plus a `ranking_filter` dimension (default: `All`).

**Usage:**

```bash
poetry run python scripts/scrape_player_stats.py --no-headless
```

**Output — `data/datasets/player_stats/{year}/player_stats.parquet`:**

`year`, `match_type`, `map_name`, `cs_version`, `ranking_filter`, `rank`, `player_id`, `player_name`, `country`, `team_id`, `team_name`, `maps_played`, `kd_diff`, `kd_ratio`, `rating`, `scraped_at`

To add more ranking filters (e.g. `Top20`, `Top50`), extend `STATS_RANKING_FILTERS` in `conf/settings.py`.

---

## Overview — completeness check

Compares the theoretical set of combinations against what is stored locally. Reports any missing combos, missing parquet files, and row counts per year.

```bash
poetry run python scripts/overview.py
```

Output saved to `data/debug_overview/overview.txt` (human-readable) and `overview.json` (machine-readable).

---

## Debug tools

```bash
# fetch and dump team/player stats page HTML + filter options
poetry run python scripts/debug_fetch_team_stats.py
poetry run python scripts/debug_fetch_player_stats.py

# download HTML for a specific match (for selector inspection)
poetry run python scripts/debug_fetch_match.py 2209322

# download a sample of match pages per year (recent + oldest + random)
poetry run python scripts/debug_sample_matches.py
poetry run python scripts/debug_sample_matches.py --year 2024
```

---

## Project layout

```
main.py                              # CLI entry point for match results scraping
src/hltv_scraper/
  conf/settings.py                   # all config: URLs, selectors, paths, delays
  models.py                          # Pydantic models
  modules/
    results/                         # match results parsers
      page.py                        # results-list page: fetch, paginate, parse rows
      matches.py                     # match header parser
      maps.py                        # per-map names and scores parser
      player_stats.py                # per-player stats parser
    stats/
      teams.py                       # team stats URL builder, combos, table parser
      players.py                     # player stats URL builder, combos, table parser
    overview/
      checker.py                     # theoretical vs local completeness checker
  utils/
    browser.py                       # camoufox session, Cloudflare wait, cookies
    html.py                          # HTML helpers
    log.py                           # logging setup
    parsers.py                       # URL builders and ID extractors
    storage.py                       # Parquet read/write
scripts/
  scrape_team_stats.py               # team stats scraper (resumes via progress.json)
  scrape_player_stats.py             # player stats scraper (resumes via progress.json)
  overview.py                        # completeness check for all datasets
  debug_fetch_team_stats.py
  debug_fetch_player_stats.py
  debug_sample_matches.py
data/
  datasets/
    results/{year}/                  # match results Parquet files
    team_stats/{year}/               # team stats Parquet files
    player_stats/{year}/             # player stats Parquet files
    debug_overview/                  # overview reports
  debug_match/                       # debug HTML files
```
