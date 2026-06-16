import json
from pathlib import Path

import polars as pl

from ..conf.settings import DATA_DIR
from ..models import MatchDetail
from .log import get_logger, log_call

log = get_logger(__name__)

# maps_json is stored as a JSON string to avoid 3-level nesting in Parquet.
# The ETL unpacks it into the maps + player_stats tables in SQLite.
_SCHEMA: dict = {
    "match_id":    pl.Int64,
    "date":        pl.String,
    "year":        pl.Int32,
    "month":       pl.Int32,
    "match_time":  pl.String,
    "team1":       pl.String,
    "team2":       pl.String,
    "score_team1": pl.Int32,
    "score_team2": pl.Int32,
    "event":       pl.String,
    "stage":       pl.String,
    "format":      pl.String,
    "maps_json":   pl.String,
    "match_url":   pl.String,
}


def _to_row(m: MatchDetail) -> dict:
    maps_data = [
        {
            "order": mp.order,
            "name": mp.name,
            "score_team1": mp.score_team1,
            "score_team2": mp.score_team2,
            "players_team1":    [p.model_dump() for p in mp.players_team1],
            "players_team2":    [p.model_dump() for p in mp.players_team2],
            "players_team1_ct": [p.model_dump() for p in mp.players_team1_ct],
            "players_team2_ct": [p.model_dump() for p in mp.players_team2_ct],
            "players_team1_t":  [p.model_dump() for p in mp.players_team1_t],
            "players_team2_t":  [p.model_dump() for p in mp.players_team2_t],
        }
        for mp in m.maps
    ]
    return {
        "match_id":    m.match_id,
        "date":        m.date.isoformat(),
        "year":        m.date.year,
        "month":       m.date.month,
        "match_time":  m.match_time,
        "team1":       m.team1,
        "team2":       m.team2,
        "score_team1": m.score_team1,
        "score_team2": m.score_team2,
        "event":       m.event,
        "stage":       m.stage,
        "format":      m.format,
        "maps_json":   json.dumps(maps_data, ensure_ascii=False),
        "match_url":   m.match_url,
    }


def load_saved_ids(year: int) -> set[int]:
    """Return match_ids already saved WITH map data for the given year (used to resume scraping).

    Matches saved with empty maps_json ('[]') are excluded so they get re-scraped.
    Matches with no mapholder on HLTV will naturally produce '[]' again — that is fine.
    """
    folder = Path(DATA_DIR) / str(year)
    files = list(folder.glob("*.parquet")) if folder.exists() else []
    if not files:
        return set()
    df = pl.concat([pl.read_parquet(f).select(["match_id", "maps_json"]) for f in files])
    with_data = df.filter(
        pl.col("maps_json").is_not_null() & (pl.col("maps_json") != "[]")
    )
    log.info(
        "%d: %d/%d matches with map data (rest will be re-scraped)",
        year, len(with_data), len(df),
    )
    return set(with_data["match_id"].to_list())


def append_to_parquet(matches: list[MatchDetail], year: int) -> None:
    """
    Upsert matches into the existing monthly Parquet files.
    Reads the current month file, appends new rows (deduplicating by match_id), and rewrites.
    """
    by_month: dict[int, list[MatchDetail]] = {}
    for m in matches:
        by_month.setdefault(m.date.month, []).append(m)

    for month, month_matches in sorted(by_month.items()):
        folder = Path(DATA_DIR) / str(year)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{month:02d}.parquet"

        new_df = pl.from_dicts([_to_row(m) for m in month_matches], schema_overrides=_SCHEMA)

        if path.exists():
            existing = pl.read_parquet(path)
            df = pl.concat([existing, new_df]).unique(subset=["match_id"], keep="last")
        else:
            df = new_df

        df.write_parquet(path, compression="zstd")
        log.debug("Parquet updated: %s  (%d rows total)", path, len(df))


@log_call
def save_year_to_parquet(matches: list[MatchDetail], year: int) -> list[Path]:
    """Save/overwrite matches grouped by month into data/datasets/{year}/{month:02d}.parquet."""
    by_month: dict[int, list[MatchDetail]] = {}
    for m in matches:
        by_month.setdefault(m.date.month, []).append(m)

    saved: list[Path] = []
    for month, month_matches in sorted(by_month.items()):
        folder = Path(DATA_DIR) / str(year)
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{month:02d}.parquet"

        df = pl.from_dicts([_to_row(m) for m in month_matches], schema_overrides=_SCHEMA)
        df.write_parquet(path, compression="zstd")
        saved.append(path)
        log.info("Saved: %s  (%d matches)", path, len(month_matches))

    return saved


def load_all_parquets() -> pl.LazyFrame:
    """Read all Parquet files under datasets/ as a unified LazyFrame."""
    if not list(Path(DATA_DIR).glob("**/*.parquet")):
        raise FileNotFoundError(f"No .parquet files found in {DATA_DIR}/")
    return pl.scan_parquet(f"{DATA_DIR}/**/*.parquet")
