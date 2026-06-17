from pathlib import Path

import polars as pl

from ..conf.settings import DATA_DIR
from ..models import MatchDetail
from .log import get_logger, log_call

log = get_logger(__name__)

# --- Parquet schemas -----------------------------------------------------------
# Three files per year under data/datasets/{year}/
#   matches.parquet      — one row per match
#   maps.parquet         — one row per map played (map_order 0 = "All Maps" aggregate)
#   player_stats.parquet — one row per player per map per side (both / ct / t)

_MATCHES_SCHEMA: dict = {
    "match_id":     pl.Int64,
    "date":         pl.String,
    "year":         pl.Int32,
    "month":        pl.Int32,
    "match_time":   pl.String,
    "team1":        pl.String,
    "team2":        pl.String,
    "score_team1":  pl.Int32,
    "score_team2":  pl.Int32,
    "event":        pl.String,
    "stage":        pl.String,
    "format":       pl.String,
    "match_url":    pl.String,
    "team1_lineup": pl.String,   # pipe-separated player nicks, e.g. "s1mple|NiKo|device|..."
    "team2_lineup": pl.String,
}

_MAPS_SCHEMA: dict = {
    "match_id":    pl.Int64,
    "map_order":   pl.Int32,
    "map_name":    pl.String,
    "score_team1": pl.Int32,
    "score_team2": pl.Int32,
}

_STATS_SCHEMA: dict = {
    "match_id":    pl.Int64,
    "map_order":   pl.Int32,
    "team":        pl.Int32,
    "side":        pl.String,
    "player_name": pl.String,
    "kills":       pl.Int32,
    "deaths":      pl.Int32,
    "adr":         pl.Float64,
    "kast":        pl.Float64,
    "rating":      pl.Float64,
}


# --- Row builders -------------------------------------------------------------

def _match_row(m: MatchDetail) -> dict:
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
        "match_url":   m.match_url,
    }


def _map_rows(m: MatchDetail) -> list[dict]:
    return [
        {
            "match_id":    m.match_id,
            "map_order":   mp.order,
            "map_name":    mp.name,
            "score_team1": mp.score_team1,
            "score_team2": mp.score_team2,
        }
        for mp in m.maps
    ]


def _stat_rows(m: MatchDetail) -> list[dict]:
    rows = []
    for mp in m.maps:
        for team, side, players in [
            (1, "both", mp.players_team1),
            (2, "both", mp.players_team2),
            (1, "ct",   mp.players_team1_ct),
            (2, "ct",   mp.players_team2_ct),
            (1, "t",    mp.players_team1_t),
            (2, "t",    mp.players_team2_t),
        ]:
            for p in players:
                rows.append({
                    "match_id":    m.match_id,
                    "map_order":   mp.order,
                    "team":        team,
                    "side":        side,
                    "player_name": p.name,
                    "kills":       p.kills,
                    "deaths":      p.deaths,
                    "adr":         p.adr,
                    "kast":        p.kast,
                    "rating":      p.rating,
                })
    return rows


# --- Parquet I/O --------------------------------------------------------------

def _upsert(path: Path, new_df: pl.DataFrame, keys: list[str]) -> None:
    if new_df.is_empty():
        return
    if path.exists():
        existing = pl.read_parquet(path)
        # add columns present in new_df but missing in existing (schema evolution)
        for col, dtype in new_df.schema.items():
            if col not in existing.columns:
                existing = existing.with_columns(pl.lit(None).cast(dtype).alias(col))
        df = pl.concat([existing.select(new_df.columns), new_df]).unique(subset=keys, keep="last")
    else:
        df = new_df
    df.write_parquet(path, compression="zstd")


def clear_year(year: int) -> None:
    """Delete all three Parquet files for the given year."""
    _delete_part(year, "matches.parquet")
    _delete_part(year, "maps.parquet")
    _delete_part(year, "player_stats.parquet")


def clear_matches(year: int) -> None:
    _delete_part(year, "matches.parquet")


def clear_maps(year: int) -> None:
    _delete_part(year, "maps.parquet")


def clear_player_stats(year: int) -> None:
    _delete_part(year, "player_stats.parquet")


def _delete_part(year: int, filename: str) -> None:
    path = Path(DATA_DIR) / str(year) / filename
    if path.exists():
        path.unlink()
        log.info("Deleted: %s", path)


# --- Load helpers for resume / reprocessing ----------------------------------

def load_saved_ids(year: int) -> set[int]:
    """match_ids already in matches.parquet (used to skip on resume)."""
    path = Path(DATA_DIR) / str(year) / "matches.parquet"
    if not path.exists():
        return set()
    df = pl.read_parquet(path).select("match_id")
    log.info("%d: %d match(es) already in matches.parquet", year, len(df))
    return set(df["match_id"].to_list())


def load_saved_map_ids(year: int) -> set[int]:
    """match_ids already in maps.parquet."""
    path = Path(DATA_DIR) / str(year) / "maps.parquet"
    if not path.exists():
        return set()
    return set(pl.read_parquet(path).select("match_id").unique()["match_id"].to_list())


def load_saved_stat_ids(year: int) -> set[int]:
    """match_ids already in player_stats.parquet."""
    path = Path(DATA_DIR) / str(year) / "player_stats.parquet"
    if not path.exists():
        return set()
    return set(pl.read_parquet(path).select("match_id").unique()["match_id"].to_list())


def load_match_records(year: int) -> list[dict]:
    """Return (match_id, match_url, score_team1, score_team2) dicts from matches.parquet."""
    path = Path(DATA_DIR) / str(year) / "matches.parquet"
    if not path.exists():
        return []
    cols = ["match_id", "match_url", "score_team1", "score_team2"]
    return pl.read_parquet(path).select(cols).drop_nulls(subset=["match_url"]).to_dicts()


# --- Per-part save functions --------------------------------------------------

def save_matches(rows: list[dict], year: int) -> None:
    if not rows:
        return
    folder = _year_folder(year)
    _upsert(
        folder / "matches.parquet",
        pl.from_dicts(rows, schema_overrides=_MATCHES_SCHEMA),
        ["match_id"],
    )


def save_maps(rows: list[dict], year: int) -> None:
    if not rows:
        return
    folder = _year_folder(year)
    _upsert(
        folder / "maps.parquet",
        pl.from_dicts(rows, schema_overrides=_MAPS_SCHEMA),
        ["match_id", "map_order"],
    )


def save_player_stats(rows: list[dict], year: int) -> None:
    if not rows:
        return
    folder = _year_folder(year)
    _upsert(
        folder / "player_stats.parquet",
        pl.from_dicts(rows, schema_overrides=_STATS_SCHEMA),
        ["match_id", "map_order", "team", "side", "player_name"],
    )


def _year_folder(year: int) -> Path:
    folder = Path(DATA_DIR) / str(year)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def append_to_parquets(matches: list[MatchDetail], year: int) -> None:
    """Convenience wrapper: upsert a batch into all three Parquet files."""
    match_rows = [_match_row(m) for m in matches]
    map_rows   = [r for m in matches for r in _map_rows(m)]
    stat_rows  = [r for m in matches for r in _stat_rows(m)]

    save_matches(match_rows, year)
    save_maps(map_rows, year)
    save_player_stats(stat_rows, year)

    log.debug(
        "Parquets updated (year=%d): %d matches | %d maps | %d stat rows",
        year, len(match_rows), len(map_rows), len(stat_rows),
    )


# --- Read helpers for notebooks / analysis ------------------------------------

def load_all_matches() -> pl.LazyFrame:
    """All matches across all years as a LazyFrame."""
    return pl.scan_parquet(f"{DATA_DIR}/**/matches.parquet")


def load_all_maps() -> pl.LazyFrame:
    """All map results (incl. map_order=0 All Maps aggregate) as a LazyFrame."""
    return pl.scan_parquet(f"{DATA_DIR}/**/maps.parquet")


def load_all_player_stats() -> pl.LazyFrame:
    """All player stats (both/ct/t sides) as a LazyFrame."""
    return pl.scan_parquet(f"{DATA_DIR}/**/player_stats.parquet")
