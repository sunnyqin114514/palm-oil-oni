# -*- coding: utf-8 -*-
"""
Build Malaysia monthly weather features from NASA POWER regional exports.

Inputs:
  data/raw/meteo/nasa_power_malaysia_prcp_monthly_2007_2025.csv
  data/raw/meteo/nasa_power_malaysia_t2m_monthly_2007_2025.csv

If the CSV files are still in ~/Downloads, this script copies them into
data/raw/meteo/ first. The original NOAA station files are kept as legacy
inputs; this NASA POWER regional table covers Malaysian production areas more
broadly and is kept as a clean monthly weather data asset.

Output:
  data/processed/meteo/nasa_power_malaysia_weather_monthly.csv
"""

from __future__ import annotations

import shutil
from pathlib import Path
from io import StringIO

import pandas as pd


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw" / "meteo"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed" / "meteo"
DOWNLOADS = Path.home() / "Downloads"

RAW_PRCP = DATA_RAW / "nasa_power_malaysia_prcp_monthly_2007_2025.csv"
RAW_T2M = DATA_RAW / "nasa_power_malaysia_t2m_monthly_2007_2025.csv"
OUT_CSV = DATA_PROCESSED / "nasa_power_malaysia_weather_monthly.csv"

MONTH_COLUMNS = {
    "JAN": "01",
    "FEB": "02",
    "MAR": "03",
    "APR": "04",
    "MAY": "05",
    "JUN": "06",
    "JUL": "07",
    "AUG": "08",
    "SEP": "09",
    "OCT": "10",
    "NOV": "11",
    "DEC": "12",
}


def ensure_raw_inputs() -> None:
    """Copy the two recent NASA POWER CSV downloads into raw/meteo if needed."""
    DATA_RAW.mkdir(parents=True, exist_ok=True)
    candidates = [
        DOWNLOADS / "POWER_Regional_Monthly_2007_2025.csv",
        DOWNLOADS / "POWER_Regional_Monthly_2007_2025-2.csv",
    ]
    if RAW_PRCP.exists() and RAW_T2M.exists():
        return

    for candidate in candidates:
        if not candidate.exists():
            continue
        text = candidate.read_text(encoding="utf-8", errors="replace")[:1200]
        if "PRECTOTCORR_SUM" in text and not RAW_PRCP.exists():
            shutil.copy2(candidate, RAW_PRCP)
        elif "T2M" in text and not RAW_T2M.exists():
            shutil.copy2(candidate, RAW_T2M)

    missing = [str(p) for p in (RAW_PRCP, RAW_T2M) if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "Missing NASA POWER raw CSV files. Expected files: " + ", ".join(missing)
        )


def read_power_csv(path: Path, expected_parameter: str, value_name: str) -> pd.DataFrame:
    """Read a NASA POWER regional monthly CSV and return monthly regional mean."""
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = "-END HEADER-"
    if marker in text:
        text = text.split(marker, 1)[1].lstrip()
    df = pd.read_csv(StringIO(text))
    required = {"PARAMETER", "YEAR", "LAT", "LON", *MONTH_COLUMNS.keys()}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"{path.name} missing required columns: {sorted(missing)}")

    df = df[df["PARAMETER"] == expected_parameter].copy()
    if df.empty:
        raise ValueError(f"{path.name} does not contain parameter {expected_parameter}")

    month_cols = list(MONTH_COLUMNS.keys())
    long = df.melt(
        id_vars=["PARAMETER", "YEAR", "LAT", "LON"],
        value_vars=month_cols,
        var_name="MONTH_NAME",
        value_name=value_name,
    )
    long[value_name] = pd.to_numeric(long[value_name], errors="coerce")
    long = long[long[value_name] != -999]
    long["YM"] = (
        long["YEAR"].astype(int).astype(str)
        + "-"
        + long["MONTH_NAME"].map(MONTH_COLUMNS)
    )

    out = (
        long.groupby("YM", as_index=False)
        .agg(
            **{
                value_name: (value_name, "mean"),
                f"{value_name}_GRID_COUNT": (value_name, "count"),
                "LAT_MIN": ("LAT", "min"),
                "LAT_MAX": ("LAT", "max"),
                "LON_MIN": ("LON", "min"),
                "LON_MAX": ("LON", "max"),
            }
        )
        .sort_values("YM")
        .reset_index(drop=True)
    )
    return out


def build_monthly() -> pd.DataFrame:
    """Merge precipitation and temperature into one model-ready monthly table."""
    ensure_raw_inputs()
    prcp = read_power_csv(RAW_PRCP, "PRECTOTCORR_SUM", "PRCP")
    temp = read_power_csv(RAW_T2M, "T2M", "TAVG_C")
    monthly = prcp.merge(
        temp[["YM", "TAVG_C", "TAVG_C_GRID_COUNT"]],
        on="YM",
        how="outer",
    ).sort_values("YM").reset_index(drop=True)

    monthly["MONTH"] = monthly["YM"].str[-2:].astype(int)
    baseline = monthly[(monthly["YM"] >= "2007-01") & (monthly["YM"] <= "2024-12")]
    climatology = baseline.groupby("MONTH")["TAVG_C"].mean().rename("TAVG_C_CLIMATOLOGY")
    monthly = monthly.merge(climatology, on="MONTH", how="left")
    monthly["TAVG_C_ANOMALY"] = monthly["TAVG_C"] - monthly["TAVG_C_CLIMATOLOGY"]

    for col in ("PRCP", "TAVG_C", "TAVG_C_CLIMATOLOGY", "TAVG_C_ANOMALY"):
        monthly[col] = monthly[col].round(3)

    monthly["SOURCE"] = "NASA POWER regional monthly"
    monthly["PRCP_UNIT"] = "mm/month"
    monthly["TAVG_UNIT"] = "C"
    return monthly[
        [
            "YM",
            "PRCP",
            "TAVG_C",
            "TAVG_C_CLIMATOLOGY",
            "TAVG_C_ANOMALY",
            "PRCP_GRID_COUNT",
            "TAVG_C_GRID_COUNT",
            "LAT_MIN",
            "LAT_MAX",
            "LON_MIN",
            "LON_MAX",
            "SOURCE",
            "PRCP_UNIT",
            "TAVG_UNIT",
        ]
    ]


def main() -> None:
    DATA_PROCESSED.mkdir(parents=True, exist_ok=True)
    monthly = build_monthly()
    monthly.to_csv(OUT_CSV, index=False)
    print(f"[ok] raw precipitation -> {RAW_PRCP}")
    print(f"[ok] raw temperature   -> {RAW_T2M}")
    print(f"[ok] monthly weather rows={len(monthly)} -> {OUT_CSV}")
    print(f"[range] {monthly['YM'].min()} ~ {monthly['YM'].max()}")
    print(
        "[missing] PRCP={} TAVG_C={} TAVG_C_ANOMALY={}".format(
            int(monthly["PRCP"].isna().sum()),
            int(monthly["TAVG_C"].isna().sum()),
            int(monthly["TAVG_C_ANOMALY"].isna().sum()),
        )
    )
    print("[tail]")
    print(monthly.tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
