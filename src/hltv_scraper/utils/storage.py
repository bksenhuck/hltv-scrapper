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
    "match_url":   pl.String,
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
        df = pl.concat([existing, new_df]).unique(subset=keys, keep="last")
    else:
        df = new_df
    df.write_parquet(path, compression="zstd")


def load_saved_ids(year: int) -> set[int]:
    """Return all match_ids already present in matches.parquet for the given year.

    A match in matches.parquet was fully scraped (even if HLTV had no stats for it),
    so it is not re-scraped on resume.
    """
    path = Path(DATA_DIR) / str(year) / "matches.parquet"
    if not path.exists():
        return set()
    df = pl.read_parquet(path).select("match_id")
    log.info("%d: %d match(es) already scraped", year, len(df))
    return set(df["match_id"].to_list())


def append_to_parquets(matches: list[MatchDetail], year: int) -> None:
    """Upsert a batch of matches into the three Parquet files for the given year."""
    folder = Path(DATA_DIR) / str(year)
    folder.mkdir(parents=True, exist_ok=True)

    match_rows = [_match_row(m) for m in matches]
    map_rows   = [r for m in matches for r in _map_rows(m)]
    stat_rows  = [r for m in matches for r in _stat_rows(m)]

    _upsert(
        folder / "matches.parquet",
        pl.from_dicts(match_rows, schema_overrides=_MATCHES_SCHEMA),
        ["match_id"],
    )
    if map_rows:
        _upsert(
            folder / "maps.parquet",
            pl.from_dicts(map_rows, schema_overrides=_MAPS_SCHEMA),
            ["match_id", "map_order"],
        )
    if stat_rows:
        _upsert(
            folder / "player_stats.parquet",
            pl.from_dicts(stat_rows, schema_overrides=_STATS_SCHEMA),
            ["match_id", "map_order", "team", "side", "player_name"],
        )

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
