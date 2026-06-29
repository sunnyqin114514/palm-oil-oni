# -*- coding: utf-8 -*-
"""
Build Malaysia monthly temperature features from NOAA daily station data.

Input:
  data/raw/meteo/马来西亚平均温度.csv

Output:
  data/processed/meteo/malaysia_temperature_monthly.csv

Notes:
  The raw file is daily NOAA-style station data in Fahrenheit. The production
  model is monthly, so this script aggregates daily TAVG to a monthly mean and
  converts Fahrenheit to Celsius. TMAX/TMIN are kept as optional reference
  columns but should not drive the model because their raw missing rates are
  high.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
DATA_RAW_METEO = PROJECT_ROOT / "data" / "raw" / "meteo"
DATA_PROCESSED_METEO = PROJECT_ROOT / "data" / "processed" / "meteo"

RAW_CSV = DATA_RAW_METEO / "马来西亚平均温度.csv"
OUT_CSV = DATA_PROCESSED_METEO / "malaysia_temperature_monthly.csv"


def fahrenheit_to_celsius(series: pd.Series) -> pd.Series:
    """Convert a numeric Fahrenheit series to Celsius."""
    return (series - 32.0) * 5.0 / 9.0


def build_monthly(raw_csv: Path = RAW_CSV) -> pd.DataFrame:
    """Aggregate daily station temperature to a monthly feature table."""
    raw = pd.read_csv(raw_csv, skiprows=2, parse_dates=["Date"])
    required = {
        "Date",
        "TAVG (Degrees Fahrenheit)",
        "TMAX (Degrees Fahrenheit)",
        "TMIN (Degrees Fahrenheit)",
    }
    missing = required.difference(raw.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    raw = raw.rename(
        columns={
            "Date": "DATE",
            "TAVG (Degrees Fahrenheit)": "TAVG_F",
            "TMAX (Degrees Fahrenheit)": "TMAX_F",
            "TMIN (Degrees Fahrenheit)": "TMIN_F",
        }
    )
    for col in ("TAVG_F", "TMAX_F", "TMIN_F"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw = raw.dropna(subset=["DATE"])
    raw["YM"] = raw["DATE"].dt.strftime("%Y-%m")

    monthly = (
        raw.groupby("YM", as_index=False)
        .agg(
            TAVG_F=("TAVG_F", "mean"),
            TMAX_F=("TMAX_F", "mean"),
            TMIN_F=("TMIN_F", "mean"),
            DAYS_REPORTED=("DATE", "count"),
            TAVG_DAYS=("TAVG_F", lambda s: int(s.notna().sum())),
            TMAX_DAYS=("TMAX_F", lambda s: int(s.notna().sum())),
            TMIN_DAYS=("TMIN_F", lambda s: int(s.notna().sum())),
        )
        .sort_values("YM")
        .reset_index(drop=True)
    )
    monthly["TAVG_C"] = fahrenheit_to_celsius(monthly["TAVG_F"])
    monthly["TMAX_C"] = fahrenheit_to_celsius(monthly["TMAX_F"])
    monthly["TMIN_C"] = fahrenheit_to_celsius(monthly["TMIN_F"])
    monthly["TAVG_C"] = monthly["TAVG_C"].round(3)
    monthly["TMAX_C"] = monthly["TMAX_C"].round(3)
    monthly["TMIN_C"] = monthly["TMIN_C"].round(3)

    # Month-of-year climatology lets the model use temperature anomalies rather
    # than raw tropical temperature levels.
    monthly["MONTH"] = monthly["YM"].str[-2:].astype(int)
    baseline = monthly[(monthly["YM"] >= "2007-01") & (monthly["YM"] <= "2024-12")]
    climatology = baseline.groupby("MONTH")["TAVG_C"].mean().rename("TAVG_C_CLIMATOLOGY")
    monthly = monthly.merge(climatology, on="MONTH", how="left")
    monthly["TAVG_C_ANOMALY"] = monthly["TAVG_C"] - monthly["TAVG_C_CLIMATOLOGY"]
    monthly["TAVG_C_CLIMATOLOGY"] = monthly["TAVG_C_CLIMATOLOGY"].round(3)
    monthly["TAVG_C_ANOMALY"] = monthly["TAVG_C_ANOMALY"].round(3)

    return monthly[
        [
            "YM",
            "TAVG_C",
            "TAVG_C_CLIMATOLOGY",
            "TAVG_C_ANOMALY",
            "TAVG_F",
            "TMAX_C",
            "TMIN_C",
            "DAYS_REPORTED",
            "TAVG_DAYS",
            "TMAX_DAYS",
            "TMIN_DAYS",
        ]
    ]


def main() -> None:
    DATA_PROCESSED_METEO.mkdir(parents=True, exist_ok=True)
    monthly = build_monthly()
    monthly.to_csv(OUT_CSV, index=False)
    since_2007 = monthly[monthly["YM"] >= "2007-01"]
    print(f"[ok] monthly rows={len(monthly)} -> {OUT_CSV}")
    print(f"[range] {monthly['YM'].min()} ~ {monthly['YM'].max()}")
    print(f"[2007+] rows={len(since_2007)} missing_TAVG={int(since_2007['TAVG_C'].isna().sum())}")
    print("[tail]")
    print(since_2007.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
