# -*- coding: utf-8 -*-
"""day14_import_ecmwf_seasonal_forecast.py — 导入 ECMWF/Copernicus 季节预测 NetCDF。

输入:
  data/raw/meteo/ecmwf_seasonal_forecast_malaysia_202606_lead1-6.nc

输出:
  data/processed/meteo/ecmwf_seasonal_forecast_malaysia_grid.csv
  data/processed/meteo/ecmwf_seasonal_forecast_malaysia_regional_mean.csv

说明:
  - NetCDF 原文件保留在 raw/meteo, 不改动原始文件。
  - grid.csv 保留每个集合成员、每个网格点的原始预测粒度。
  - regional_mean.csv 是给后续模型使用的区域/集合平均表。
"""
from __future__ import annotations

import calendar
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import xarray as xr


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_NC = DATA_DIR / "raw" / "meteo" / "ecmwf_seasonal_forecast_malaysia_202606_lead1-6.nc"
OUT_GRID = DATA_DIR / "processed" / "meteo" / "ecmwf_seasonal_forecast_malaysia_grid.csv"
OUT_MEAN = DATA_DIR / "processed" / "meteo" / "ecmwf_seasonal_forecast_malaysia_regional_mean.csv"


def _target_month(reference_time: pd.Timestamp, leadtime_month: int) -> pd.Timestamp:
    """CDS 口径: leadtime_month=1 是起报当月, 所以目标月 = 起报月 + lead-1。"""
    return reference_time.to_period("M").to_timestamp() + pd.DateOffset(months=leadtime_month - 1)


def _month_seconds(month_start: pd.Timestamp) -> int:
    days = calendar.monthrange(month_start.year, month_start.month)[1]
    return days * 24 * 60 * 60


def _scalar_attr(attrs: Dict[str, Any], key: str, default: Any = "") -> Any:
    value = attrs.get(key, default)
    if hasattr(value, "item"):
        return value.item()
    return value


def build_grid_table(path: Path = RAW_NC) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"找不到 ECMWF NetCDF 文件: {path}")

    ds = xr.open_dataset(path, engine="h5netcdf")
    required_vars = {"t2m", "tprate"}
    missing_vars = required_vars.difference(ds.data_vars)
    if missing_vars:
        raise ValueError(f"NetCDF 缺少必要变量: {sorted(missing_vars)}")

    t2m = ds["t2m"]
    tprate = ds["tprate"]
    t2m_units = str(t2m.attrs.get("units", ""))
    tprate_units = str(tprate.attrs.get("units", ""))
    if t2m_units != "K":
        raise ValueError(f"t2m 单位不是 K, 当前为: {t2m_units}")
    if tprate_units != "m s**-1":
        raise ValueError(f"tprate 单位不是 m s**-1, 当前为: {tprate_units}")

    ref_times = pd.to_datetime(ds["forecast_reference_time"].values)
    leadtimes = [int(v) for v in ds["forecastMonth"].values]
    rows: List[Dict[str, Any]] = []

    for ref_idx, ref_time in enumerate(ref_times):
        reference_ts = pd.Timestamp(ref_time)
        for lead_idx, leadtime in enumerate(leadtimes):
            target_ts = _target_month(reference_ts, leadtime)
            seconds = _month_seconds(target_ts)
            for member in ds["number"].values:
                for lat in ds["latitude"].values:
                    for lon in ds["longitude"].values:
                        selector = {
                            "number": member,
                            "forecast_reference_time": ds["forecast_reference_time"].values[ref_idx],
                            "forecastMonth": leadtime,
                            "latitude": lat,
                            "longitude": lon,
                        }
                        t2m_k = float(t2m.sel(selector).values)
                        rate_m_s = float(tprate.sel(selector).values)
                        rows.append({
                            "SOURCE_FILE": path.name,
                            "INSTITUTION": ds.attrs.get("institution", ""),
                            "FORECAST_REFERENCE_TIME": reference_ts.strftime("%Y-%m-%d"),
                            "LEADTIME_MONTH": leadtime,
                            "TARGET_YM": target_ts.strftime("%Y-%m"),
                            "ENSEMBLE_MEMBER": int(member),
                            "LAT": float(lat),
                            "LON": float(lon),
                            "T2M_K": t2m_k,
                            "T2M_C": t2m_k - 273.15,
                            "TPRATE_M_PER_S": rate_m_s,
                            "PRCP_MM_PER_MONTH": rate_m_s * seconds * 1000,
                            "ECMWF_SYSTEM": _scalar_attr(t2m.attrs, "GRIB_system", ""),
                        })

    return pd.DataFrame(rows).sort_values(
        ["FORECAST_REFERENCE_TIME", "LEADTIME_MONTH", "ENSEMBLE_MEMBER", "LAT", "LON"]
    ).reset_index(drop=True)


def build_regional_mean(grid: pd.DataFrame) -> pd.DataFrame:
    group_cols = ["FORECAST_REFERENCE_TIME", "LEADTIME_MONTH", "TARGET_YM"]
    return (
        grid.groupby(group_cols, as_index=False)
        .agg(
            T2M_C_MEAN=("T2M_C", "mean"),
            PRCP_MM_PER_MONTH_MEAN=("PRCP_MM_PER_MONTH", "mean"),
            ENSEMBLE_MEMBERS=("ENSEMBLE_MEMBER", "nunique"),
            GRID_POINTS=("LAT", "count"),
            LAT_MIN=("LAT", "min"),
            LAT_MAX=("LAT", "max"),
            LON_MIN=("LON", "min"),
            LON_MAX=("LON", "max"),
        )
        .sort_values(group_cols)
        .reset_index(drop=True)
    )


def main() -> None:
    OUT_GRID.parent.mkdir(parents=True, exist_ok=True)
    grid = build_grid_table(RAW_NC)
    regional_mean = build_regional_mean(grid)

    grid.to_csv(OUT_GRID, index=False)
    regional_mean.to_csv(OUT_MEAN, index=False)

    print(f"[ECMWF grid] {OUT_GRID} rows={len(grid)}")
    print(f"[ECMWF mean] {OUT_MEAN} rows={len(regional_mean)}")
    if not regional_mean.empty:
        print(regional_mean.to_string(index=False))


if __name__ == "__main__":
    main()
