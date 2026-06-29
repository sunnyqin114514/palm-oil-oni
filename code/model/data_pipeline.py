# -*- coding: utf-8 -*-
"""第一阶段：从三本 Excel 归档构建棕榈油单产建模数据集。

输入只使用三本正式 Excel:
  data/processed/archives/01_palm_oil_planted_area_malaysia.xlsx
  data/processed/archives/02_climate_data_malaysia.xlsx
  data/processed/archives/03_palm_oil_production_malaysia.xlsx

输出:
  data/processed/product/palm_oil_model_dataset.csv
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ARCHIVE_DIR = PROJECT_ROOT / "data" / "processed" / "archives"
OUT_DIR = PROJECT_ROOT / "data" / "processed" / "product"

AREA_XLSX = ARCHIVE_DIR / "01_palm_oil_planted_area_malaysia.xlsx"
CLIMATE_XLSX = ARCHIVE_DIR / "02_climate_data_malaysia.xlsx"
PRODUCTION_XLSX = ARCHIVE_DIR / "03_palm_oil_production_malaysia.xlsx"
OUT_CSV = OUT_DIR / "palm_oil_model_dataset.csv"


def _require_columns(df: pd.DataFrame, columns: Iterable[str], source: str) -> None:
    missing = set(columns).difference(df.columns)
    if missing:
        raise ValueError(f"{source} 缺少必要字段: {sorted(missing)}")


def _to_month(value: pd.Series) -> pd.Series:
    """把日期列统一成 YYYY-MM 月度字符串。"""
    return pd.to_datetime(value, errors="coerce").dt.to_period("M").astype(str)


def read_area_monthly(
    path: Path = AREA_XLSX,
    backcast_start_year: int | None = None,
) -> pd.DataFrame:
    """读取 MPOB 年频成熟面积，并展开为月频。

    当 backcast_start_year 不为 None 时，使用 MPOB 已有年份 (2015-2025) 对 YEAR 做
    线性回归，外推得到 [backcast_start_year, 最早已知年份-1] 的成熟/未成熟/总面积，
    用于把样本窗口前推 1-2 年。外推年份会在 Area_Source 列中标记为 "BACKCAST"，
    实际年份标记为 "MPOB"。
    """
    area = pd.read_excel(path, sheet_name="01_MPOB_Mature_Area")
    _require_columns(
        area,
        ["YEAR", "MATURE_HECTARES", "IMMATURE_HECTARES", "TOTAL_HECTARES"],
        "01_MPOB_Mature_Area",
    )

    area = area.rename(
        columns={
            "MATURE_HECTARES": "Mature_Area",
            "IMMATURE_HECTARES": "Immature_Area",
            "TOTAL_HECTARES": "Total_Area",
        }
    )
    area["YEAR"] = pd.to_numeric(area["YEAR"], errors="coerce")
    for col in ["Mature_Area", "Immature_Area", "Total_Area"]:
        area[col] = pd.to_numeric(area[col], errors="coerce")

    area = area.dropna(subset=["YEAR", "Mature_Area"]).copy()
    if area.empty:
        raise ValueError("成熟面积数据为空，无法计算 Yield。")
    if (area["Mature_Area"] <= 0).any():
        raise ValueError("成熟面积存在小于等于 0 的值，无法计算 Yield。")

    area = area.sort_values("YEAR").reset_index(drop=True)
    known_rows: List[Dict[str, Any]] = []
    for row in area.itertuples(index=False):
        year = int(row.YEAR)
        for month in range(1, 13):
            known_rows.append(
                {
                    "Date": f"{year:04d}-{month:02d}",
                    "Mature_Area": float(row.Mature_Area),
                    "Immature_Area": float(row.Immature_Area),
                    "Total_Area": float(row.Total_Area),
                    "Area_Source": "MPOB",
                }
            )

    backcast_rows: List[Dict[str, Any]] = []
    if backcast_start_year is not None:
        from scipy import stats as _stats  # 局部引入，避免顶层依赖

        first_year = int(area["YEAR"].min())
        if backcast_start_year < first_year:
            years = area["YEAR"].to_numpy(dtype=float)
            fitted: Dict[str, Tuple[float, float]] = {}
            for col in ["Mature_Area", "Immature_Area", "Total_Area"]:
                slope, intercept, _, _, _ = _stats.linregress(years, area[col].to_numpy(dtype=float))
                fitted[col] = (slope, intercept)
            for yr in range(backcast_start_year, first_year):
                for col, (slope, intercept) in fitted.items():
                    val = intercept + slope * yr
                    if val <= 0:
                        raise ValueError(f"外推 {col} 在 {yr} 年为非正值 ({val:.0f})，请缩小外推区间。")
                for month in range(1, 13):
                    backcast_rows.append(
                        {
                            "Date": f"{yr:04d}-{month:02d}",
                            "Mature_Area": float(fitted["Mature_Area"][1] + fitted["Mature_Area"][0] * yr),
                            "Immature_Area": float(fitted["Immature_Area"][1] + fitted["Immature_Area"][0] * yr),
                            "Total_Area": float(fitted["Total_Area"][1] + fitted["Total_Area"][0] * yr),
                            "Area_Source": "BACKCAST",
                        }
                    )

    return pd.DataFrame(backcast_rows + known_rows)


def read_climate_history(path: Path = CLIMATE_XLSX) -> pd.DataFrame:
    """读取气候 Excel 中唯一口径的历史降水、气温、ONI。"""
    prcp = pd.read_excel(path, sheet_name="01_MY_PRCP_History")
    tavg = pd.read_excel(path, sheet_name="02_MY_TAVG_History")
    oni = pd.read_excel(path, sheet_name="03_ONI_Monthly")

    _require_columns(prcp, ["YM", "PRCP"], "01_MY_PRCP_History")
    _require_columns(tavg, ["YM", "TAVG_C"], "02_MY_TAVG_History")
    _require_columns(oni, ["YM", "ONI"], "03_ONI_Monthly")

    prcp = prcp.rename(columns={"YM": "Date"}).copy()
    tavg = tavg.rename(columns={"YM": "Date", "TAVG_C": "TAVG"}).copy()
    oni = oni.rename(columns={"YM": "Date"}).copy()

    for df in [prcp, tavg, oni]:
        df["Date"] = df["Date"].astype(str).str.slice(0, 7)

    prcp["PRCP"] = pd.to_numeric(prcp["PRCP"], errors="coerce")
    tavg["TAVG"] = pd.to_numeric(tavg["TAVG"], errors="coerce")
    oni["ONI"] = pd.to_numeric(oni["ONI"], errors="coerce")

    weather = prcp[["Date", "PRCP"]].merge(tavg[["Date", "TAVG"]], on="Date", how="outer")
    climate = weather.merge(oni[["Date", "ONI"]], on="Date", how="left")
    return climate.sort_values("Date").reset_index(drop=True)


def read_production_monthly(path: Path = PRODUCTION_XLSX) -> pd.DataFrame:
    """读取 iFinD 月度产量原始表，并统一为月频。"""
    prod = pd.read_excel(path, sheet_name="Production_Monthly_iFinD")
    _require_columns(prod, ["DATE", "VALUE"], "Production_Monthly_iFinD")

    prod = prod.rename(columns={"VALUE": "Production"}).copy()
    prod["Date"] = _to_month(prod["DATE"])
    prod["Production"] = pd.to_numeric(prod["Production"], errors="coerce")
    prod = prod.dropna(subset=["Date", "Production"])
    if prod.empty:
        raise ValueError("产量数据为空，无法构建模型数据集。")

    return prod[["Date", "Production"]].sort_values("Date").reset_index(drop=True)


def enrich_climate_timeline(climate: pd.DataFrame) -> pd.DataFrame:
    """在完整气候时间轴上计算: 同月气候常态、月度距平、3 月滚动距平、ONI_lag12。

    在完整时间轴 (2007-01 起) 上做 rolling, 确保模型窗口起点 (2015-01) 时
    3 月滚动距平已经稳定生效, 不会因清洗而损失行数。
    """
    timeline = climate.sort_values("Date").reset_index(drop=True).copy()
    timeline["Month"] = pd.to_datetime(timeline["Date"]).dt.month

    climatology = (
        timeline.groupby("Month", as_index=False)
        .agg(PRCP_CLIM=("PRCP", "mean"), TAVG_CLIM=("TAVG", "mean"))
    )
    timeline = timeline.merge(climatology, on="Month", how="left")
    timeline["PRCP_DEV"] = timeline["PRCP"] - timeline["PRCP_CLIM"]
    timeline["TAVG_DEV"] = timeline["TAVG"] - timeline["TAVG_CLIM"]

    rolling_window = 3
    timeline["PRCP_DEV_3m"] = (
        timeline["PRCP_DEV"].rolling(window=rolling_window, min_periods=rolling_window).mean()
    )
    timeline["TAVG_DEV_3m"] = (
        timeline["TAVG_DEV"].rolling(window=rolling_window, min_periods=rolling_window).mean()
    )

    oni_lag = timeline[["Date", "ONI"]].dropna(subset=["ONI"]).copy()
    oni_lag["Date"] = (
        pd.to_datetime(oni_lag["Date"]) + pd.DateOffset(months=12)
    ).dt.to_period("M").astype(str)
    oni_lag = oni_lag.rename(columns={"ONI": "ONI_lag12"})

    enriched = timeline.merge(oni_lag, on="Date", how="left")
    return enriched


TREND_BASELINE_YM = "2010-01"

# 面积线性外推的起点年份：MPOB 最早 2015，前推到 2010 给样本外留更充裕的窗口。
AREA_BACKCAST_START_YEAR = 2010


def _trend_index(date_strings: pd.Series) -> pd.Series:
    """以 2010-01 为 0, 之后每月 +1 的连续月份索引, 用于线性趋势项。"""
    base = pd.Period(TREND_BASELINE_YM, freq="M")
    periods = pd.to_datetime(date_strings).dt.to_period("M")
    return (periods - base).apply(lambda p: int(p.n))


def build_dataset(
    area_backcast_start_year: int | None = AREA_BACKCAST_START_YEAR,
) -> pd.DataFrame:
    area = read_area_monthly(backcast_start_year=area_backcast_start_year)
    climate = enrich_climate_timeline(read_climate_history())
    production = read_production_monthly()

    merged = (
        production.merge(climate, on="Date", how="left")
        .merge(area, on="Date", how="left")
        .sort_values("Date")
        .reset_index(drop=True)
    )
    merged["Yield"] = merged["Production"] / merged["Mature_Area"]
    merged["Trend"] = _trend_index(merged["Date"])

    required = [
        "Date",
        "Production",
        "Mature_Area",
        "Yield",
        "Trend",
        "ONI_lag12",
        "PRCP",
        "TAVG",
        "PRCP_DEV",
        "TAVG_DEV",
        "PRCP_DEV_3m",
        "TAVG_DEV_3m",
        "Month",
    ]
    df_clean = merged.dropna(subset=required).copy()
    if df_clean.empty:
        raise ValueError("清洗后 df_clean 为空，请检查三本 Excel 的时间范围是否重叠。")

    ordered_columns = [
        "Date",
        "Production",
        "Mature_Area",
        "Immature_Area",
        "Total_Area",
        "Area_Source",
        "Yield",
        "Trend",
        "ONI_lag12",
        "PRCP",
        "TAVG",
        "PRCP_CLIM",
        "TAVG_CLIM",
        "PRCP_DEV",
        "TAVG_DEV",
        "PRCP_DEV_3m",
        "TAVG_DEV_3m",
        "Month",
    ]
    return df_clean[ordered_columns].reset_index(drop=True)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df_clean = build_dataset()
    df_clean.to_csv(OUT_CSV, index=False)

    print(f"[ok] df_clean rows={len(df_clean)} -> {OUT_CSV}")
    print(f"[range] {df_clean['Date'].min()} ~ {df_clean['Date'].max()}")
    print(
        "[missing] "
        + ", ".join(f"{col}={int(df_clean[col].isna().sum())}" for col in df_clean.columns)
    )
    print("[sample]")
    print(df_clean.head(3).to_string(index=False))


if __name__ == "__main__":
    main()
