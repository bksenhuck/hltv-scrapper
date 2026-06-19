"""Compare theoretical vs local state for all scrape datasets.

Verifica quantos combos foram processados, quais estão faltando,
e se os parquets por ano existem e têm dados.

Output:
  data/debug_overview/overview.txt   — relatório legível
  data/debug_overview/overview.json  — resumo em JSON

Usage:
    poetry run python scripts/overview.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hltv_scraper.conf.settings import (
    STATS_PLAYERS_DATA_DIR,
    STATS_PLAYERS_PARQUET,
    STATS_TEAMS_DATA_DIR,
    STATS_TEAMS_PARQUET,
)
from src.hltv_scraper.modules.overview.checker import (
    DatasetOverview,
    check_dataset,
    format_report,
)
from src.hltv_scraper.modules.stats.players import (
    combo_key as player_key,
    get_all_combinations as player_combos,
)
from src.hltv_scraper.modules.stats.teams import (
    combo_key as team_key,
    get_all_combinations as team_combos,
)

OUT_DIR = Path("data/debug_overview")


def _to_json(ov: DatasetOverview) -> dict:
    return {
        "name": ov.name,
        "complete": ov.complete,
        "total_expected": ov.total_expected,
        "total_done": ov.total_done,
        "total_gap": ov.total_gap,
        "total_rows": ov.total_rows,
        "years": [
            {
                "year": y.year,
                "complete": y.complete,
                "expected": y.expected,
                "done": y.done,
                "gap": y.gap,
                "rows": y.rows,
                "parquet_exists": y.parquet_path is not None,
                "columns": y.columns,
                "missing_combos": y.missing,
            }
            for y in ov.years
        ],
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    team_ov = check_dataset(
        name="team_stats",
        data_dir=Path(STATS_TEAMS_DATA_DIR),
        parquet_name=STATS_TEAMS_PARQUET,
        all_combos=team_combos(),
        key_fn=lambda c: team_key(*c),
        year_fn=lambda c: str(c[0]),
    )

    player_ov = check_dataset(
        name="player_stats",
        data_dir=Path(STATS_PLAYERS_DATA_DIR),
        parquet_name=STATS_PLAYERS_PARQUET,
        all_combos=player_combos(),
        key_fn=lambda c: player_key(*c),
        year_fn=lambda c: str(c[0]),
    )

    # ── text report ────────────────────────────────────────────────
    lines = [f"HLTV Scraper Overview — {generated_at}", ""]
    for ov in [team_ov, player_ov]:
        lines += format_report(ov)
        lines.append("")

    report_path = OUT_DIR / "overview.txt"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    # print to stdout
    print("\n".join(lines))
    print(f"Saved: {report_path}")

    # ── JSON summary ───────────────────────────────────────────────
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "datasets": [_to_json(team_ov), _to_json(player_ov)],
    }
    json_path = OUT_DIR / "overview.json"
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
