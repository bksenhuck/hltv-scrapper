"""
ETL: data/datasets/{year}/{month}.parquet → hltv.db (SQLite)

Tables:
  matches      — one row per match
  maps         — one row per map played
  player_stats — one row per player per map, per side ('both', 'ct', 't')

Usage:
  python etl.py                  # process all Parquet files in data/datasets/
  python etl.py --year 2024      # only files for 2024
  python etl.py --reset          # drop and recreate the database before inserting
"""
import argparse
import json
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
    name        TEXT    NOT NULL,
    score_team1 INTEGER NOT NULL,
    score_team2 INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS player_stats (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id      INTEGER NOT NULL REFERENCES maps(id),
    team        INTEGER NOT NULL,              -- 1 or 2
    side        TEXT    NOT NULL DEFAULT 'both',  -- 'both', 'ct', 't'
    player_name TEXT    NOT NULL,
    kills       INTEGER,
    deaths      INTEGER,
    adr         REAL,
    kast        REAL,
    rating      REAL
);

CREATE INDEX IF NOT EXISTS idx_matches_year   ON matches(year);
CREATE INDEX IF NOT EXISTS idx_matches_date   ON matches(date);
CREATE INDEX IF NOT EXISTS idx_matches_team1  ON matches(team1);
CREATE INDEX IF NOT EXISTS idx_matches_team2  ON matches(team2);
CREATE INDEX IF NOT EXISTS idx_maps_match     ON maps(match_id);
CREATE INDEX IF NOT EXISTS idx_stats_map      ON player_stats(map_id);
CREATE INDEX IF NOT EXISTS idx_stats_player   ON player_stats(player_name);
CREATE INDEX IF NOT EXISTS idx_stats_side     ON player_stats(side);
"""


def _find_parquets(year: int | None) -> list[Path]:
    base = Path(DATA_DIR)
    pattern = f"{year}/*.parquet" if year else "**/*.parquet"
    files = sorted(base.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No .parquet files found in {DATA_DIR}/ (pattern: {pattern})")
    return files


def _insert(conn: sqlite3.Connection, df: pl.DataFrame) -> tuple[int, int, int]:
    matches_n = maps_n = stats_n = 0

    for row in df.iter_rows(named=True):
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO matches
                    (match_id, date, year, month, match_time,
                     team1, team2, score_team1, score_team2,
                     event, stage, format, match_url)
                VALUES (?,?,?,?,?, ?,?,?,?, ?,?,?,?)
                """,
                (
                    row["match_id"], row["date"], row["year"], row["month"], row.get("match_time"),
                    row["team1"], row["team2"], row["score_team1"], row["score_team2"],
                    row.get("event"), row.get("stage"), row.get("format"), row.get("match_url"),
                ),
            )
            if not conn.execute("SELECT changes()").fetchone()[0]:
                continue  # already exists — skip maps and stats to avoid duplicates
            matches_n += 1

            maps_data = json.loads(row.get("maps_json") or "[]")
            for mp in maps_data:
                cur = conn.execute(
                    """
                    INSERT INTO maps (match_id, map_order, name, score_team1, score_team2)
                    VALUES (?,?,?,?,?)
                    """,
                    (row["match_id"], mp["order"], mp["name"], mp["score_team1"], mp["score_team2"]),
                )
                map_id = cur.lastrowid
                maps_n += 1

                sides = [
                    (1, "both", "players_team1"),
                    (2, "both", "players_team2"),
                    (1, "ct",   "players_team1_ct"),
                    (2, "ct",   "players_team2_ct"),
                    (1, "t",    "players_team1_t"),
                    (2, "t",    "players_team2_t"),
                ]
                for team_num, side, key in sides:
                    for p in mp.get(key, []):
                        conn.execute(
                            """
                            INSERT INTO player_stats
                                (map_id, team, side, player_name, kills, deaths, adr, kast, rating)
                            VALUES (?,?,?,?,?,?,?,?,?)
                            """,
                            (
                                map_id, team_num, side, p["name"],
                                p.get("kills"), p.get("deaths"),
                                p.get("adr"), p.get("kast"), p.get("rating"),
                            ),
                        )
                        stats_n += 1

        except (sqlite3.Error, json.JSONDecodeError) as e:
            print(f"  Error match_id={row.get('match_id')}: {e}")

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

    files = _find_parquets(args.year)
    print(f"Parquet files: {len(files)}")
    for f in files:
        print(f"  {f}")

    df = pl.concat([pl.read_parquet(f) for f in files])
    print(f"\nRows loaded: {len(df)}")

    with sqlite3.connect(db_path) as conn:
        conn.executescript(DDL)
        matches_n, maps_n, stats_n = _insert(conn, df)
        conn.commit()

    print(f"\nETL complete → {db_path}")
    print(f"  Matches inserted    : {matches_n}")
    print(f"  Maps inserted       : {maps_n}")
    print(f"  Player stats        : {stats_n}")


if __name__ == "__main__":
    main()
