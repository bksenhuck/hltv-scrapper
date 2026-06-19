# modules/

Scraping logic split into three sub-packages: `results/`, `stats/`, and `overview/`.

---

## results/

Parses match data from HLTV results pages and individual match pages.

```
results/
  page.py          fetch and parse results-list pages (pagination + match rows)
  matches.py       parse match header (time, event, stage, format)
  maps.py          parse per-map names and scores
  player_stats.py  parse per-player stats per map per side
```

The three parsers (`matches`, `maps`, `player_stats`) all receive the **same HTML string** fetched once per match. They are independent — any subset can run via `--parts` in `main.py`.

### page.py

**`fetch_page_html(page, url) -> str | None`**  
Loads a results page and waits for the results container. Saves `debug_page.html` on failure.

**`parse_total_pages(html) -> int | None`**  
Reads `.pagination-data` to estimate the number of pages for the year.

**`parse_results(html) -> list[MatchResult]`**  
Extracts match rows from `.results-sublist` blocks:
```
.results-sublist
  .standard-headline   ← date heading
  .result-con a        ← one anchor per match (team names, scores, event, URL)
```

### matches.py

**`parse_match_row(html, match, match_id) -> dict`**  
Parses match-level header fields. Falls back to the `MatchResult` values from the results page for missing fields.

| Field | Selector |
|---|---|
| `match_time` | `.timeAndEvent .date` / `.timeAndEvent .time` |
| `event` | `.timeAndEvent .text-ellipsis` |
| `stage` | `.timeAndEvent .preposition + a` |
| `format` | `.veto-box .standard-box`, regex `Best of N` |

### maps.py

**`parse_map_rows(html, match_id, s1, s2) -> list[dict]`**  
Parses `.mapholder` elements. Generates a `map_order=0` "All Maps" aggregate row only when `.matchstats > .stats-content` exists (i.e. HLTV has stats for the match).

### player_stats.py

**`parse_stat_rows(html, match_id) -> list[dict]`**  
Iterates `.stats-content` sections. Each section contains six tables: `totalstats`, `ctstats`, `tstats` for team 1 then team 2.

| Stat | Selector |
|---|---|
| `player_name` | `.player-nick` |
| `kills`, `deaths` | `td.kd` (`traditional-data` cell) |
| `adr` | `td.adr` (`traditional-data` cell) |
| `kast` | `td.kast` (strips `%`) |
| `rating` | `td.rating` |

---

## stats/

Scrapes the HLTV stats overview pages (`/stats/teams`, `/stats/players`) across all filter combinations.

```
stats/
  teams.py    URL builder, combination generator, table parser for /stats/teams
  players.py  URL builder, combination generator, table parser for /stats/players
```

Both modules share the same structure:

| Function | Purpose |
|---|---|
| `get_all_combinations()` | Returns every `(year, match_type, map, cs_version[, ranking])` tuple |
| `build_*_stats_url(...)` | Assembles the HLTV URL for a given combination |
| `combo_key(...)` | Returns a stable string key used in `progress.json` |
| `parse_*_stats_table(html, ...)` | Parses the `table.stats-table` and returns a list of row dicts |

**Dimensions per scrape:** 16 years × 6 match types × 14 maps × 3 CS versions = **4 032 combinations**.

Output schema — `teams.py`: `year`, `match_type`, `map_name`, `cs_version`, `rank`, `team_id`, `team_name`, `country`, `maps_played`, `kd_diff`, `kd_ratio`, `rating`, `scraped_at`

Output schema — `players.py`: same + `ranking_filter`, `player_id`, `player_name` (replaces `team_name` at rank position), `team_id`, `team_name`

---

## overview/

Checks dataset completeness: compares the theoretical combination set against what is stored locally.

```
overview/
  checker.py   DatasetOverview / YearSummary dataclasses + check_dataset() + format_report()
```

### checker.py

**`check_dataset(name, data_dir, parquet_name, all_combos, key_fn, year_fn) -> DatasetOverview`**  
Generic checker. Loads `progress.json`, groups combos by year, and for each year reports:
- `expected` / `done` / `gap` combo counts
- `missing` combo keys (for re-scraping)
- whether the parquet file exists and how many rows it has

**`format_report(overview) -> list[str]`**  
Returns a formatted text table ready to print or write to file.

Consumed by `scripts/overview.py`, which runs both team and player datasets and saves results to `data/debug_overview/`.
