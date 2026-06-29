# -*- coding: utf-8 -*-
"""
Build Malaysia crude palm oil production files from iFinD EDB raw data.

Input:
  data/raw/product/ifind_edb_palm_oil_production_my.csv

Outputs:
  data/processed/product/palm_oil_production_my_monthly.csv
  data/processed/product/palm_oil_production_my_weekly_estimated.csv

Important:
  iFinD indicator S002958800 is monthly. The weekly file is an estimate, not a
  true weekly observation. Method: allocate each monthly total evenly to all
  calendar days in the month, then sum those daily estimates into Monday-Sunday
  weeks. This keeps the total volume equal to the monthly raw data.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
DATA_RAW_PRODUCT = PROJECT_ROOT / "data" / "raw" / "product"
DATA_PROCESSED_PRODUCT = PROJECT_ROOT / "data" / "processed" / "product"

RAW_CSV = DATA_RAW_PRODUCT / "ifind_edb_palm_oil_production_my.csv"
MONTHLY_CSV = DATA_PROCESSED_PRODUCT / "palm_oil_production_my_monthly.csv"
WEEKLY_CSV = DATA_PROCESSED_PRODUCT / "palm_oil_production_my_weekly_estimated.csv"


def build_monthly(raw_csv: Path = RAW_CSV) -> pd.DataFrame:
    """Clean iFinD raw EDB output into an ascending monthly production table."""
    raw = pd.read_csv(raw_csv, parse_dates=["DATE"])
    required = {"DATE", "ID", "INDEX_NAME", "VALUE", "RTIME"}
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    monthly = raw.rename(columns={"VALUE": "CPO_PRODUCTION_TONNES"}).copy()
    monthly["CPO_PRODUCTION_TONNES"] = pd.to_numeric(
        monthly["CPO_PRODUCTION_TONNES"], errors="coerce"
    )
    monthly = monthly.dropna(subset=["DATE", "CPO_PRODUCTION_TONNES"])
    monthly = monthly.sort_values("DATE").reset_index(drop=True)
    return monthly[["DATE", "ID", "INDEX_NAME", "CPO_PRODUCTION_TONNES", "RTIME"]]


def build_weekly(monthly: pd.DataFrame) -> pd.DataFrame:
    """Convert monthly totals into weekly estimates via daily even allocation."""
    daily_frames: list[pd.DataFrame] = []
    for row in monthly.itertuples(index=False):
        month_start = row.DATE.replace(day=1)
        month_end = row.DATE
        days = pd.date_range(month_start, month_end, freq="D")
        daily_value = float(row.CPO_PRODUCTION_TONNES) / len(days)
        daily_frames.append(
            pd.DataFrame(
                {
                    "DATE": days,
                    "ID": row.ID,
                    "INDEX_NAME": row.INDEX_NAME,
                    "CPO_PRODUCTION_TONNES_DAILY_EST": daily_value,
                    "SOURCE_MONTH": row.DATE.strftime("%Y-%m"),
                    "SOURCE_MONTH_RTIME": row.RTIME,
                }
            )
        )

    if not daily_frames:
        raise ValueError("No valid monthly rows to allocate.")

    daily = pd.concat(daily_frames, ignore_index=True)
    daily["WEEK_START"] = daily["DATE"] - pd.to_timedelta(daily["DATE"].dt.weekday, unit="D")
    daily["WEEK_END"] = daily["WEEK_START"] + pd.Timedelta(days=6)

    weekly = (
        daily.groupby(["WEEK_START", "WEEK_END", "ID", "INDEX_NAME"], as_index=False)
        .agg(
            CPO_PRODUCTION_TONNES_WEEKLY_EST=(
                "CPO_PRODUCTION_TONNES_DAILY_EST",
                "sum",
            ),
            DAYS_COVERED=("DATE", "count"),
            SOURCE_MONTHS=("SOURCE_MONTH", lambda s: "|".join(sorted(set(s)))),
            SOURCE_MONTH_RTIMES=("SOURCE_MONTH_RTIME", lambda s: "|".join(sorted(set(s)))),
        )
        .sort_values("WEEK_START")
        .reset_index(drop=True)
    )
    weekly["YEAR_WEEK"] = weekly["WEEK_START"].dt.strftime("%G-W%V")
    weekly["FREQUENCY"] = "weekly_estimated_from_monthly"
    weekly["METHOD"] = "monthly_total_evenly_allocated_to_days_then_summed_to_monday_sunday_week"

    return weekly[
        [
            "WEEK_START",
            "WEEK_END",
            "YEAR_WEEK",
            "ID",
            "INDEX_NAME",
            "CPO_PRODUCTION_TONNES_WEEKLY_EST",
            "DAYS_COVERED",
            "SOURCE_MONTHS",
            "SOURCE_MONTH_RTIMES",
            "FREQUENCY",
            "METHOD",
        ]
    ]


def main() -> None:
    DATA_PROCESSED_PRODUCT.mkdir(parents=True, exist_ok=True)
    monthly = build_monthly()
    weekly = build_weekly(monthly)

    monthly.to_csv(MONTHLY_CSV, index=False)
    weekly.to_csv(WEEKLY_CSV, index=False)

    monthly_sum = float(monthly["CPO_PRODUCTION_TONNES"].sum())
    weekly_sum = float(weekly["CPO_PRODUCTION_TONNES_WEEKLY_EST"].sum())
    print(f"[ok] monthly rows={len(monthly)} -> {MONTHLY_CSV}")
    print(f"[ok] weekly rows={len(weekly)} -> {WEEKLY_CSV}")
    print(f"[range] weekly {weekly['WEEK_START'].min().date()} ~ {weekly['WEEK_END'].max().date()}")
    print(f"[check] monthly_sum={monthly_sum:.3f} weekly_sum={weekly_sum:.3f} diff={weekly_sum - monthly_sum:.6f}")


if __name__ == "__main__":
    main()
