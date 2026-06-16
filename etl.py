"""
ETL: data/datasets/{year}/{matches,maps,player_stats}.parquet → hltv.db (SQLite)

Tables:
  matches      — one row per match
  maps         — one row per map played (map_order 0 = All Maps aggregate)
  player_stats — one row per player per map per side (both / ct / t)

Usage:
  python etl.py                  # process all Parquet files in data/datasets/
  python etl.py --year 2024      # only files for 2024
  python etl.py --reset          # drop and recreate the database before inserting
"""
import argparse
import sqlite3
from pathlib import Path

import polars as pl

from src.hltv_scraper.conf.settings import DATA_DIR

DB_PATH = "hltv.db"

DDL = """
CREATE TABLE IF NOT EXISTS matches (
    match_id    INTEGER PRIMARY KEY,
    date        TEXT    NOT NULL,
    year        INTEGER NOT NULL,
    month       INTEGER NOT NULL,
    match_time  TEXT,
    team1       TEXT    NOT NULL,
    team2       TEXT    NOT NULL,
    score_team1 INTEGER NOT NULL,
    score_team2 INTEGER NOT NULL,
    event       TEXT,
    stage       TEXT,
    format      TEXT,
    match_url   TEXT
);

CREATE TABLE IF NOT EXISTS maps (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    INTEGER NOT NULL REFERENCES matches(match_id),
    map_order   INTEGER NOT NULL,
    map_name    TEXT    NOT NULL,
    score_team1 INTEGER NOT NULL,
    score_team2 INTEGER NOT NULL,
    UNIQUE(match_id, map_order)
);

CREATE TABLE IF NOT EXISTS player_stats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id    INTEGER NOT NULL REFERENCES matches(match_id),
    map_order   INTEGER NOT NULL,
    team        INTEGER NOT NULL,
    side        TEXT    NOT NULL,
    player_name TEXT    NOT NULL,
    kills       INTEGER,
    deaths      INTEGER,
    adr         REAL,
    kast        REAL,
    rating      REAL,
    UNIQUE(match_id, map_order, team, side, player_name)
);

CREATE INDEX IF NOT EXISTS idx_matches_year    ON matches(year);
CREATE INDEX IF NOT EXISTS idx_matches_date    ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_team1   ON matches(team1);
CREATE INDEX IF NOT EXISTS idx_matches_team2   ON matches(team2);
CREATE INDEX IF NOT EXISTS idx_maps_match      ON maps(match_id);
CREATE INDEX IF NOT EXISTS idx_stats_match     ON player_stats(match_id);
CREATE INDEX IF NOT EXISTS idx_stats_map_order ON player_stats(map_order);
CREATE INDEX IF NOT EXISTS idx_stats_player    ON player_stats(player_name);
CREATE INDEX IF NOT EXISTS idx_stats_side      ON player_stats(side);
"""


def _load(base: Path, name: str, year: int | None) -> pl.DataFrame | None:
    pattern = f"{year}/{name}" if year else f"**/{name}"
    files = sorted(base.glob(pattern))
    return pl.concat([pl.read_parquet(f) for f in files]) if files else None


def _insert(
    conn: sqlite3.Connection,
    matches_df: pl.DataFrame,
    maps_df: pl.DataFrame | None,
    stats_df: pl.DataFrame | None,
) -> tuple[int, int, int]:
    matches_n = maps_n = stats_n = 0

    for row in matches_df.iter_rows(named=True):
        try:
            conn.execute(
                """INSERT OR IGNORE INTO matches
                    (match_id,date,year,month,match_time,team1,team2,
                     score_team1,score_team2,event,stage,format,match_url)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    row["match_id"], row["date"], row["year"], row["month"],
                    row.get("match_time"), row["team1"], row["team2"],
                    row["score_team1"], row["score_team2"],
                    row.get("event"), row.get("stage"), row.get("format"), row.get("match_url"),
                ),
            )
            matches_n += conn.execute("SELECT changes()").fetchone()[0]
        except sqlite3.Error as e:
            print(f"  Error match_id={row.get('match_id')}: {e}")

    if maps_df is not None:
        for row in maps_df.iter_rows(named=True):
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO maps (match_id,map_order,map_name,score_team1,score_team2) VALUES (?,?,?,?,?)",
                    (row["match_id"], row["map_order"], row["map_name"], row["score_team1"], row["score_team2"]),
                )
                maps_n += conn.execute("SELECT changes()").fetchone()[0]
            except sqlite3.Error as e:
                print(f"  Error map match_id={row.get('match_id')}: {e}")

    if stats_df is not None:
        for row in stats_df.iter_rows(named=True):
            try:
                conn.execute(
                    """INSERT OR IGNORE INTO player_stats
                        (match_id,map_order,team,side,player_name,kills,deaths,adr,kast,rating)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        row["match_id"], row["map_order"], row["team"], row["side"],
                        row["player_name"], row.get("kills"), row.get("deaths"),
                        row.get("adr"), row.get("kast"), row.get("rating"),
                    ),
                )
                stats_n += conn.execute("SELECT changes()").fetchone()[0]
            except sqlite3.Error as e:
                print(f"  Error stat match_id={row.get('match_id')}: {e}")

    return matches_n, maps_n, stats_n


def main():
    parser = argparse.ArgumentParser(description="ETL: Parquet → SQLite (hltv.db)")
    parser.add_argument("--year", type=int, help="Process only files for a specific year")
    parser.add_argument("--reset", action="store_true", help="Drop and recreate the database")
    parser.add_argument("--db", default=DB_PATH, help=f"SQLite path (default: {DB_PATH})")
    args = parser.parse_args()

    db_path = Path(args.db)
    if args.reset and db_path.exists():
        db_path.unlink()
        print(f"Database removed: {db_path}")

    base = Path(DATA_DIR)
    matches_df = _load(base, "matches.parquet", args.year)
    if matches_df is None:
        print(f"No matches.parquet found in {DATA_DIR}/")
        return

    maps_df  = _load(base, "maps.parquet", args.year)
    stats_df = _load(base, "player_stats.parquet", args.year)

    print(f"Matches     : {len(matches_df)}")
    print(f"Maps        : {len(maps_df) if maps_df is not None else 0}")
    print(f"Player stats: {len(stats_df) if stats_df is not None else 0}")

    with sqlite3.connect(db_path) as conn:
        conn.executescript(DDL)
        matches_n, maps_n, stats_n = _insert(conn, matches_df, maps_df, stats_df)
        conn.commit()

    print(f"\nETL complete → {db_path}")
    print(f"  Matches inserted : {matches_n}")
    print(f"  Maps inserted    : {maps_n}")
    print(f"  Player stats     : {stats_n}")


if __name__ == "__main__":
    main()
