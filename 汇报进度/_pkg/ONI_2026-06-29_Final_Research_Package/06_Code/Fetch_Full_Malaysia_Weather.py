# -*- coding: utf-8 -*-
"""抓取 NASA POWER 全马来西亚月度格点气象 (含婆罗洲沙巴/砂拉越) 2007-01 ~ 2026-05。

背景:
  现有 data/raw/POWER_Regional_Monthly_2007_2025.numbers 只覆盖经度
  100.0–109.375°E (半岛+南海), 婆罗洲 (沙巴 115–119°E, 砂拉越 109.6–115°E)
  基本缺失, 且只到 2025-12。为支持 "西马/砂拉越/沙巴三区温度×降水空间交互"
  以及 2024-2026 样本外验证, 这里重新抓取覆盖整个马来西亚
  (lon 99.375–119.5, lat 0.5–7.5) 的格点。

数据来源策略 (NASA POWER 月度端点仅到 2025-12, 2026 走日度端点聚合):
  - 2007-2025: temporal/monthly/regional  (源生月度产品, 高效)
  - 2026:      temporal/daily/regional 聚合到月 (T2M 取月内日均, PRECTOTCORR 取月内日总)
               仅保留完整月份 (到 2026-05)

输出:
  data/raw/meteo/nasa_power_grid_full_malaysia_T2M.csv          (宽表: YEAR,LAT,LON,JAN..DEC)
  data/raw/meteo/nasa_power_grid_full_malaysia_PRECTOTCORR.csv
  data/processed/meteo/nasa_power_grid_full_malaysia_monthly.csv (长表: Date,LAT,LON,T2M,PRCP)

口径说明:
  - PRECTOTCORR = 月度降水总量 (mm/month); T2M = 2 米气温月均 (°C)
  - 缺测值 -999 -> NaN; 与现有全国序列口径一致 (NASA POWER Regional 0.5x0.625 网格)
"""
from __future__ import annotations

import calendar
import io
import time
from pathlib import Path
from typing import List

import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "meteo"
PROC_DIR = PROJECT_ROOT / "data" / "processed" / "meteo"

API_MONTHLY = "https://power.larc.nasa.gov/api/temporal/monthly/regional"
API_DAILY = "https://power.larc.nasa.gov/api/temporal/daily/regional"
# (value_name, 月度端点参数名, 日度端点参数名, 2026月聚合方式)
# 注意: 月度端点 PRECTOTCORR 是 mm/天均值, 必须用 PRECTOTCORR_SUM 才是 mm/月,
#       与原始序列和日度求和口径一致。
PARAM_SPECS = [
    ("T2M", "T2M", "T2M", "mean"),
    ("PRCP", "PRECTOTCORR_SUM", "PRECTOTCORR", "sum"),
]

MONTHLY_START, MONTHLY_END = 2007, 2025
DAILY_YEAR = 2026
DAILY_LAST_FULL_MONTH = 5  # 2026 仅日度到 6 月中, 只保留完整月份 (到 5 月)

LAT_MIN, LAT_MAX = 0.5, 7.5
LON_TILES = [(99.375, 106.875), (107.5, 114.375), (115.0, 119.5)]

MONTH_COLS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN",
              "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def _get_csv(url: str, q: dict, tag: str) -> pd.DataFrame:
    last_err = None
    for attempt in range(1, 5):
        try:
            resp = requests.get(url, params=q, timeout=120)
            resp.raise_for_status()
            text = resp.text
            if "-END HEADER-" not in text:
                raise ValueError(f"返回缺少表头, 前 200 字: {text[:200]!r}")
            body = text.split("-END HEADER-", 1)[1].lstrip("\n\r")
            df = pd.read_csv(io.StringIO(body))
            if df.empty:
                raise ValueError("解析后为空表")
            return df
        except Exception as e:
            last_err = e
            wait = attempt * 5
            print(f"  [retry {attempt}] {tag} 失败: {e}; {wait}s 后重试")
            time.sleep(wait)
    raise RuntimeError(f"抓取失败 {tag}: {last_err}")


def fetch_monthly(value_name: str, month_param: str) -> pd.DataFrame:
    """2007-2025 月度宽表 -> 长表 (Date,LAT,LON,value)。"""
    frames: List[pd.DataFrame] = []
    for lon_min, lon_max in LON_TILES:
        q = {"parameters": month_param, "community": "AG",
             "latitude-min": LAT_MIN, "latitude-max": LAT_MAX,
             "longitude-min": lon_min, "longitude-max": lon_max,
             "start": MONTHLY_START, "end": MONTHLY_END, "format": "CSV"}
        print(f"[monthly] {month_param} lon[{lon_min},{lon_max}] ...")
        frames.append(_get_csv(API_MONTHLY, q, f"monthly {month_param} lon[{lon_min},{lon_max}]"))
    wide = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["YEAR", "LAT", "LON"]).reset_index(drop=True)

    wide.to_csv(RAW_DIR / f"nasa_power_grid_full_malaysia_{month_param}.csv", index=False)

    long = wide[["YEAR", "LAT", "LON"] + MONTH_COLS].melt(
        id_vars=["YEAR", "LAT", "LON"], value_vars=MONTH_COLS,
        var_name="MON", value_name=value_name)
    mon_map = {m: i + 1 for i, m in enumerate(MONTH_COLS)}
    long["Date"] = (long["YEAR"].astype(int).astype(str) + "-"
                    + long["MON"].map(mon_map).map(lambda x: f"{int(x):02d}"))
    long[value_name] = pd.to_numeric(long[value_name], errors="coerce")
    long.loc[long[value_name] <= -999, value_name] = pd.NA
    return long[["Date", "LAT", "LON", value_name]]


def fetch_daily_2026(value_name: str, daily_param: str, agg: str) -> pd.DataFrame:
    """2026 日度 -> 聚合到月 (T2M 日均 / PRECTOTCORR 日总), 长表 (Date,LAT,LON,value)。"""
    end_day = calendar.monthrange(DAILY_YEAR, DAILY_LAST_FULL_MONTH)[1]
    frames: List[pd.DataFrame] = []
    for lon_min, lon_max in LON_TILES:
        q = {"parameters": daily_param, "community": "AG",
             "latitude-min": LAT_MIN, "latitude-max": LAT_MAX,
             "longitude-min": lon_min, "longitude-max": lon_max,
             "start": f"{DAILY_YEAR}0101",
             "end": f"{DAILY_YEAR}{DAILY_LAST_FULL_MONTH:02d}{end_day:02d}",
             "format": "CSV"}
        print(f"[daily2026] {daily_param} lon[{lon_min},{lon_max}] ...")
        frames.append(_get_csv(API_DAILY, q, f"daily {daily_param} lon[{lon_min},{lon_max}]"))
    daily = pd.concat(frames, ignore_index=True).drop_duplicates(
        subset=["YEAR", "DOY", "LAT", "LON"]).reset_index(drop=True)

    daily[daily_param] = pd.to_numeric(daily[daily_param], errors="coerce")
    daily.loc[daily[daily_param] <= -999, daily_param] = pd.NA
    daily["date"] = pd.to_datetime(daily["YEAR"].astype(int).astype(str) + "-"
                                   + daily["DOY"].astype(int).astype(str), format="%Y-%j")
    daily["Date"] = daily["date"].dt.strftime("%Y-%m")

    monthly = (daily.groupby(["Date", "LAT", "LON"], as_index=False)[daily_param]
               .agg(agg).rename(columns={daily_param: value_name}))
    return monthly[["Date", "LAT", "LON", value_name]]


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    longs = {}
    for value_name, month_param, daily_param, agg in PARAM_SPECS:
        m = fetch_monthly(value_name, month_param)
        d = fetch_daily_2026(value_name, daily_param, agg)
        longs[value_name] = pd.concat([m, d], ignore_index=True)
        print(f"[ok] {value_name}: 月度 {len(m)} + 2026日聚合 {len(d)} 行")

    merged = longs["T2M"].merge(longs["PRCP"], on=["Date", "LAT", "LON"], how="outer")
    merged = merged.sort_values(["Date", "LAT", "LON"]).reset_index(drop=True)
    out = PROC_DIR / "nasa_power_grid_full_malaysia_monthly.csv"
    merged.to_csv(out, index=False)
    n_cells = merged[["LAT", "LON"]].drop_duplicates().shape[0]
    print(f"\n[ok] 全马格点长表 {len(merged)} 行 / {n_cells} 格点 / "
          f"{merged['Date'].min()}~{merged['Date'].max()} -> {out}")


if __name__ == "__main__":
    main()
