# modules/

Scraping logic, split into independent units that share common primitives.

---

## Overview

```
modules/
  common.py           shared: browser fetch + low-level HTML helpers
  results.py          results-list pages (pagination, match rows)
  scraper_matches.py  parse match header info from a match page
  scraper_maps.py     parse per-map names and scores from a match page
  scraper_stats.py    parse per-player stats from a match page
```

The three `scraper_*.py` modules are **independent of each other** and all receive the same raw HTML string from `common.fetch_match_html`. They can be called individually in `main.py` for partial reprocessing without re-scraping everything.

---

## common.py

Shared primitives used by all three scraper modules.

### `fetch_match_html(page, url, match_id) -> str | None`

Navigates to a match page with Playwright and returns the full HTML.  
Returns `None` on timeout or navigation error (the caller skips the match and continues).

```
page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
page.wait_for_selector(".mapholder", timeout=SELECTOR_TIMEOUT_MS)   ← optional, non-fatal
return page.content()
```

### `get_stats_sections(soup) -> list[Tag]`

Finds all direct-child `.stats-content` divs inside `.matchstats`.

```
.matchstats
  └── .stats-content   ← sections[0]: "All Maps" aggregate
  └── .stats-content   ← sections[1]: map 1
  └── .stats-content   ← sections[2]: map 2
  ...
```

Both `scraper_maps.py` and `scraper_stats.py` call this to locate the stats block.

### Parse helpers

| Function | Input | Output |
|---|---|---|
| `trad_cell(cells)` | list of `Tag` | the cell with class `traditional-data` (non-eco-adjusted) |
| `parse_kd(cells)` | list of `td.kd` cells | `(kills, deaths)` parsed from `"46-23"` |
| `float_cell(el)` | single `Tag` | `float` or `None` |
| `float_pct(el)` | single `Tag` | strips `%` and returns float (e.g. `72.7%` → `72.7`) |

---

## results.py

Handles the HLTV results-list pages.

### `fetch_page_html(page, url) -> str | None`

Loads a results page, dismisses consent banners, and waits for the results container. Falls back through several CSS selectors and a string search before giving up. Saves `debug_page.html` on failure.

### `parse_total_pages(html) -> int | None`

Reads `.pagination-data` to estimate the number of pages for the year.  
Supports `data-total`, `data-pages`, and text formats like `"1-100 of 3847"`.

### `parse_results(html) -> list[MatchResult]`

Extracts `MatchResult` objects from a results page:

```
.results-sublist          ← one block per date
  .standard-headline      ← date heading (parsed by utils/parsers.py)
  .result-con a.a-reset   ← one anchor per match
    .team × 2             ← team names
    .result-score span × 2 ← final scores (maps won)
    .event-name           ← event name
```

Each `MatchResult` contains the full match URL, which is the key used to deduplicate on resume.

---

## scraper_matches.py

### `parse_match_row(html, match, match_id) -> dict`

Parses match-level header fields from the individual match page HTML. Also receives the `MatchResult` from the results page (used as fallback for team names, scores, event name).

**Selectors used:**

| Field | Selector |
|---|---|
| `match_time` | `.timeAndEvent .date` then `.timeAndEvent .time` |
| `event` | `.timeAndEvent .text-ellipsis` (falls back to results-page value) |
| `stage` | `.timeAndEvent .preposition + a`, or regex on `.timeAndEvent` text |
| `format` | `.veto-box .standard-box` text, regex `Best of N` |

**Returns** one dict matching the `matches.parquet` schema:

```python
{
  "match_id", "date", "year", "month", "match_time",
  "team1", "team2", "score_team1", "score_team2",
  "event", "stage", "format", "match_url"
}
```

**Does not parse** maps or player stats — those are handled by the other two modules.

---

## scraper_maps.py

### `parse_map_rows(html, match_id, series_score_t1, series_score_t2) -> list[dict]`

Parses map names and per-map scores from `.mapholder` elements. Also generates a `map_order=0` "All Maps" aggregate row using the series scores passed as arguments.

**HTML structure parsed:**

```
.mapholder (× N, one per map)
  .mapname          ← map name (skipped if "TBA" or empty)
  .results-team-score × 2  ← round scores for this map
```

The "All Maps" aggregate (`map_order=0`) is generated only when `.matchstats > .stats-content` exists, confirming that HLTV has stats data for this match. Matches without any stats block produce an empty list.

**Returns** list of dicts matching the `maps.parquet` schema:

```python
{"match_id", "map_order", "map_name", "score_team1", "score_team2"}
```

**map_order alignment:** `map_order=1` in maps.parquet corresponds to `sections[1]` in `scraper_stats.py` (both skip the index-0 "All Maps" slot).

---

## scraper_stats.py

### `parse_stat_rows(html, match_id) -> list[dict]`

Parses player stats from all `.stats-content` sections. Iterates with `enumerate(get_stats_sections(...))` so `map_order` matches directly: index 0 → All Maps, index 1 → map 1, etc.

**HTML structure per `.stats-content` section:**

```
.stats-content
  table.totalstats × 2    ← team1, team2 — "both" side
  table.ctstats × 2       ← team1, team2 — CT side (may have class "hidden")
  table.tstats × 2        ← team1, team2 — T side  (may have class "hidden")
```

Each table has a `tbody` with one `tr` per player. For each player row:

| Stat | Selector | Notes |
|---|---|---|
| `player_name` | `.player-nick` | |
| `kills`, `deaths` | `td.kd` | format `"46-23"`, picks `traditional-data` cell |
| `adr` | `td.adr` | picks `traditional-data` cell |
| `kast` | `td.kast` | picks `traditional-data` cell, strips `%` |
| `rating` | `td.rating` | direct cell (not `.rating2`) |

**Returns** list of dicts matching the `player_stats.parquet` schema:

```python
{
  "match_id", "map_order", "team",      # 1 or 2
  "side",                                # "both" | "ct" | "t"
  "player_name", "kills", "deaths",
  "adr", "kast", "rating"
}
```

Old matches (pre-2016 roughly) have ADR and KAST as `None`/`0.0` — HLTV did not track those metrics then.

---

## Data flow

```
results.py
  parse_results(html) → list[MatchResult]
        │
        │  (for each new match_id)
        ▼
common.py
  fetch_match_html(page, url, match_id) → html
        │
        ├──► scraper_matches.parse_match_row(html, match, match_id)  → dict
        ├──► scraper_maps.parse_map_rows(html, match_id, s1, s2)     → list[dict]
        └──► scraper_stats.parse_stat_rows(html, match_id)           → list[dict]
                                                │
                                                ▼
                                    storage.save_matches / save_maps / save_player_stats
                                    → data/datasets/{year}/*.parquet
```

In `run_all` (default in `main.py`) all three parsers receive the **same HTML** fetched once per match. When `--parts` is used, only the relevant parser runs and only its Parquet file is updated.
