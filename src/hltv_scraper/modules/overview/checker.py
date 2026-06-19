"""Compare theoretical combinations vs local state for a scrape dataset."""
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import polars as pl


@dataclass
class YearSummary:
    year: str
    expected: int
    done: int
    missing: list[str]
    parquet_path: Path | None
    rows: int | None
    columns: list[str] = field(default_factory=list)

    @property
    def gap(self) -> int:
        return self.expected - self.done

    @property
    def complete(self) -> bool:
        return self.gap == 0


@dataclass
class DatasetOverview:
    name: str
    data_dir: Path
    parquet_name: str
    years: list[YearSummary]

    @property
    def total_expected(self) -> int:
        return sum(y.expected for y in self.years)

    @property
    def total_done(self) -> int:
        return sum(y.done for y in self.years)

    @property
    def total_gap(self) -> int:
        return self.total_expected - self.total_done

    @property
    def total_rows(self) -> int:
        return sum(y.rows or 0 for y in self.years)

    @property
    def complete(self) -> bool:
        return self.total_gap == 0


def check_dataset(
    name: str,
    data_dir: Path,
    parquet_name: str,
    all_combos: list[tuple],
    key_fn: Callable[[tuple], str],
    year_fn: Callable[[tuple], str],
) -> DatasetOverview:
    """Generic checker for any scrape dataset.

    all_combos : full list of expected (year, ...) tuples
    key_fn     : combo → progress key string (same as combo_key())
    year_fn    : combo → year string for grouping
    """
    progress_file = data_dir / "progress.json"
    done_keys: set[str] = set()
    if progress_file.exists():
        done_keys = set(json.loads(progress_file.read_text(encoding="utf-8")))

    # group by year
    by_year: dict[str, list[tuple]] = {}
    for combo in all_combos:
        y = year_fn(combo)
        by_year.setdefault(y, []).append(combo)

    year_summaries: list[YearSummary] = []
    for year_val in sorted(by_year.keys(), key=lambda x: ("0" if x == "all" else x)):
        combos = by_year[year_val]
        missing = [key_fn(c) for c in combos if key_fn(c) not in done_keys]
        done = len(combos) - len(missing)

        parquet_path = data_dir / str(year_val) / parquet_name
        rows: int | None = None
        columns: list[str] = []
        if parquet_path.exists():
            try:
                df = pl.read_parquet(parquet_path)
                rows = len(df)
                columns = df.columns
            except Exception:
                rows = -1

        year_summaries.append(YearSummary(
            year=year_val,
            expected=len(combos),
            done=done,
            missing=missing,
            parquet_path=parquet_path if parquet_path.exists() else None,
            rows=rows,
            columns=columns,
        ))

    return DatasetOverview(
        name=name,
        data_dir=data_dir,
        parquet_name=parquet_name,
        years=year_summaries,
    )


def format_report(overview: DatasetOverview) -> list[str]:
    status = "COMPLETE" if overview.complete else f"INCOMPLETE — {overview.total_gap} combos missing"
    lines = [
        "=" * 65,
        f"Dataset : {overview.name}",
        f"Dir     : {overview.data_dir}",
        f"Status  : {status}",
        f"Combos  : {overview.total_done}/{overview.total_expected}",
        f"Rows    : {overview.total_rows:,}",
        "=" * 65,
        f"{'Year':8s}  {'Done/Expected':>16s}  {'Rows':>9s}  Parquet",
        f"{'-'*8}  {'-'*16}  {'-'*9}  {'-'*10}",
    ]

    for y in overview.years:
        combo_str = f"{y.done}/{y.expected}"
        flag = "OK" if y.complete else f"!! {y.gap} missing"
        row_str = f"{y.rows:,}" if y.rows is not None and y.rows >= 0 else ("ERROR" if y.rows == -1 else "—")
        parquet_str = "exists" if y.parquet_path else "MISSING"
        lines.append(f"{y.year:8s}  {combo_str:>11s}  {flag:>10s}  {row_str:>9s}  {parquet_str}")

    if not overview.complete:
        lines.append("")
        lines.append("MISSING COMBOS (first 10 per year):")
        for y in overview.years:
            if y.missing:
                lines.append(f"  [{y.year}] {len(y.missing)} missing:")
                for m in y.missing[:10]:
                    lines.append(f"    {m}")
                if len(y.missing) > 10:
                    lines.append(f"    ... and {len(y.missing) - 10} more")

    return lines
