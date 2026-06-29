# -*- coding: utf-8 -*-
"""构建温度深化研究 + 三维预测模型用的扩展数据集 (2010-01 ~ 2026-05)。

相比第一阶段 data_pipeline.py, 本数据集:
  1. 全国气温/降水直接取自全马格点旧框均值 (含 2026, 与历史国家序列口径完全一致);
  2. 新增三区 (West/Sarawak/Sabah) 气温/降水距平, 支持空间交互研究;
  3. 成熟面积: 2015-2025 真实 MPOB; 2026 用近 3 年线性趋势外推 (FORECAST);
     可选 2010-2014 全样本线性回推 (BACKCAST, 仅供"含外推"敏感性变体, 有高估局限);
  4. 保留原始月度距平 (未滚动), 让下游脚本自由搜索积温窗口长度。

输出:
  data/processed/product/palm_oil_extended_dataset.csv

口径:
  - 气候常态 = 同日历月在 2007-2025 上的均值 (不含 2026, 避免基准被半年数据污染)
  - Yield = Production / Mature_Area
  - Trend = 自 2010-01 起的连续月份索引 (吸收结构性年际增长)
  - ONI_lag12 = 12 个月前的 ONI (沿用第一阶段领先期结论)
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ARCHIVE_DIR = PROJECT_ROOT / "data" / "processed" / "archives"
METEO_DIR = PROJECT_ROOT / "data" / "processed" / "meteo"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "product"

AREA_XLSX = ARCHIVE_DIR / "01_palm_oil_planted_area_malaysia.xlsx"
CLIMATE_XLSX = ARCHIVE_DIR / "02_climate_data_malaysia.xlsx"
PRODUCTION_XLSX = ARCHIVE_DIR / "03_palm_oil_production_malaysia.xlsx"
GRID_CSV = METEO_DIR / "nasa_power_grid_full_malaysia_monthly.csv"
REGIONAL_WIDE = METEO_DIR / "malaysia_regional_weather_wide.csv"
OUT_CSV = OUT_DIR / "palm_oil_extended_dataset.csv"

NAT_BOX = (100.0, 109.375, 1.0, 6.5)   # 与历史国家序列一致的旧框
CLIM_END = "2025-12"                    # 气候常态基准窗口上界
TREND_BASELINE_YM = "2010-01"
BACKCAST_START_YEAR = 2010              # 回推起点 (2010-2014)
FORECAST_YEAR = 2026                    # 面积需外推的年份
REGIONS = ["West", "Sarawak", "Sabah"]


def read_area_yearly() -> pd.DataFrame:
    a = pd.read_excel(AREA_XLSX, sheet_name="01_MPOB_Mature_Area")
    a = a.rename(columns={"MATURE_HECTARES": "Mature_Area"})
    a["YEAR"] = pd.to_numeric(a["YEAR"], errors="coerce")
    a["Mature_Area"] = pd.to_numeric(a["Mature_Area"], errors="coerce")
    a = a.dropna(subset=["YEAR", "Mature_Area"]).sort_values("YEAR").reset_index(drop=True)
    return a[["YEAR", "Mature_Area"]]


def build_area_monthly(backcast: bool) -> pd.DataFrame:
    """生成 2010-2026 的月频成熟面积, 标注来源。

    backcast=True 时补 2010-2014 (全样本线性回推); 否则只从 2015 起。
    2026 始终用近 3 年线性趋势外推 (更贴近近年面积下行)。
    """
    a = read_area_yearly()
    yrs = a["YEAR"].to_numpy(float)
    mat = a["Mature_Area"].to_numpy(float)
    first_year, last_year = int(yrs.min()), int(yrs.max())

    # 全样本线性 (用于回推, 沿用第一阶段方法)
    sl_full, ic_full, _, _, _ = stats.linregress(yrs, mat)
    # 近 3 年线性 (用于 2026 前推, 捕捉近年下行)
    sl_rec, ic_rec, _, _, _ = stats.linregress(yrs[-3:], mat[-3:])

    rows: List[Dict] = []
    # 回推 2010-2014
    if backcast:
        for y in range(BACKCAST_START_YEAR, first_year):
            val = ic_full + sl_full * y
            for m in range(1, 13):
                rows.append({"Date": f"{y}-{m:02d}", "Mature_Area": val, "Area_Source": "BACKCAST"})
    # 真实 MPOB
    for y, v in zip(yrs.astype(int), mat):
        for m in range(1, 13):
            rows.append({"Date": f"{y}-{m:02d}", "Mature_Area": float(v), "Area_Source": "MPOB"})
    # 前推 2026
    if FORECAST_YEAR > last_year:
        val = ic_rec + sl_rec * FORECAST_YEAR
        for m in range(1, 13):
            rows.append({"Date": f"{FORECAST_YEAR}-{m:02d}", "Mature_Area": val, "Area_Source": "FORECAST"})

    df = pd.DataFrame(rows)
    if (df["Mature_Area"] <= 0).any():
        raise ValueError("成熟面积出现非正值, 请检查外推区间。")
    return df


def read_national_weather() -> pd.DataFrame:
    """全国气温/降水: 全马格点旧框均值 (2007-2026-05), 含同月气候常态与距平。"""
    grid = pd.read_csv(GRID_CSV)
    lo, hi, la, ha = NAT_BOX
    box = grid[(grid.LON >= lo) & (grid.LON <= hi) & (grid.LAT >= la) & (grid.LAT <= ha)]
    nat = (box.groupby("Date", as_index=False)
           .agg(TAVG=("T2M", "mean"), PRCP=("PRCP", "mean")))
    nat["Month"] = pd.to_datetime(nat["Date"]).dt.month
    clim = (nat[nat.Date <= CLIM_END].groupby("Month", as_index=False)
            .agg(TAVG_CLIM=("TAVG", "mean"), PRCP_CLIM=("PRCP", "mean")))
    nat = nat.merge(clim, on="Month", how="left")
    nat["TAVG_DEV"] = nat["TAVG"] - nat["TAVG_CLIM"]
    nat["PRCP_DEV"] = nat["PRCP"] - nat["PRCP_CLIM"]
    return nat.sort_values("Date").reset_index(drop=True)


def read_oni() -> pd.DataFrame:
    oni = pd.read_excel(CLIMATE_XLSX, sheet_name="03_ONI_Monthly")
    oni = oni.rename(columns={"YM": "Date", "ONI": "ONI"})
    oni["Date"] = oni["Date"].astype(str).str.slice(0, 7)
    oni["ONI"] = pd.to_numeric(oni["ONI"], errors="coerce")
    oni = oni.dropna(subset=["ONI"]).drop_duplicates("Date")
    lag = oni.copy()
    lag["Date"] = (pd.to_datetime(lag["Date"]) + pd.DateOffset(months=12)).dt.strftime("%Y-%m")
    lag = lag.rename(columns={"ONI": "ONI_lag12"})
    return oni.merge(lag, on="Date", how="outer").sort_values("Date").reset_index(drop=True)


def read_production() -> pd.DataFrame:
    prod = pd.read_excel(PRODUCTION_XLSX, sheet_name="Production_Monthly_iFinD")
    prod = prod.rename(columns={"VALUE": "Production"})
    prod["Date"] = pd.to_datetime(prod["DATE"], errors="coerce").dt.strftime("%Y-%m")
    prod["Production"] = pd.to_numeric(prod["Production"], errors="coerce")
    prod = prod.dropna(subset=["Date", "Production"]).drop_duplicates("Date")
    return prod[["Date", "Production"]].sort_values("Date").reset_index(drop=True)


def read_regional() -> pd.DataFrame:
    reg = pd.read_csv(REGIONAL_WIDE)
    keep = ["Date"]
    for r in REGIONS:
        keep += [f"T2M_DEV_{r}", f"PRCP_DEV_{r}", f"T2M_{r}", f"PRCP_{r}"]
    return reg[[c for c in keep if c in reg.columns]]


def _trend_index(dates: pd.Series) -> pd.Series:
    base = pd.Period(TREND_BASELINE_YM, freq="M")
    return pd.to_datetime(dates).dt.to_period("M").apply(lambda p: int((p - base).n))


def build(backcast: bool) -> pd.DataFrame:
    area = build_area_monthly(backcast=backcast)
    nat = read_national_weather()
    oni = read_oni()
    prod = read_production()
    reg = read_regional()

    df = (prod.merge(nat, on="Date", how="left")
              .merge(oni[["Date", "ONI", "ONI_lag12"]], on="Date", how="left")
              .merge(area, on="Date", how="left")
              .merge(reg, on="Date", how="left"))
    df = df[(df.Date >= "2010-01")].sort_values("Date").reset_index(drop=True)
    df["Yield"] = df["Production"] / df["Mature_Area"]
    df["Trend"] = _trend_index(df["Date"])
    df["Year"] = pd.to_datetime(df["Date"]).dt.year
    df["Month"] = pd.to_datetime(df["Date"]).dt.month

    front = ["Date", "Year", "Month", "Trend", "Production", "Mature_Area",
             "Area_Source", "Yield", "ONI", "ONI_lag12",
             "TAVG", "PRCP", "TAVG_CLIM", "PRCP_CLIM", "TAVG_DEV", "PRCP_DEV"]
    rest = [c for c in df.columns if c not in front]
    return df[front + rest]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = build(backcast=True)  # 主输出含回推, 用 Area_Source 区分, 下游可过滤
    df.to_csv(OUT_CSV, index=False)
    print(f"[ok] 扩展数据集 {len(df)} 行 / {df.Date.min()}~{df.Date.max()} -> {OUT_CSV}")
    print("[Area_Source]", df.Area_Source.value_counts().to_dict())
    miss = {c: int(df[c].isna().sum()) for c in
            ["Yield", "ONI_lag12", "TAVG_DEV", "PRCP_DEV",
             "T2M_DEV_West", "T2M_DEV_Sarawak", "T2M_DEV_Sabah"]}
    print("[missing]", miss)
    print("[2026 段]")
    print(df[df.Year == 2026][["Date", "Yield", "Mature_Area", "Area_Source",
                               "TAVG_DEV", "PRCP_DEV"]].to_string(index=False))


if __name__ == "__main__":
    main()
