"""数据载入层 (data loader)。

把集中在 data/ 下的 CSV 统一读取，给 API 与 notebook 共享。
通过 os.path 相对路径定位，无论 uvicorn 在哪个目录启动都能找到文件。
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(HERE))
CODE_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(CODE_DIR)
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

PALM_CSV = os.path.join(DATA_DIR, "raw", "product", "CPO_F_daily_yahoo.csv")
PRCP_ONI_CSV = os.path.join(
    DATA_DIR,
    "processed",
    "meteo",
    "kuala_lumpur_malaysia_prcp_noaa_nino34_pacific_oni_merged.csv",
)
ONI_LONG_CSV = os.path.join(
    DATA_DIR, "processed", "meteo", "noaa_nino34_pacific_oni_monthly.csv"
)
PRCP_REGIONAL_CSV = os.path.join(
    DATA_DIR, "processed", "meteo", "malaysia_prcp_regional.csv"
)
WEATHER_MONTHLY_CSV = os.path.join(
    DATA_DIR, "processed", "meteo", "nasa_power_malaysia_weather_monthly.csv"
)
PALM_PRODUCTION_CSV = os.path.join(
    DATA_DIR, "processed", "product", "palm_oil_production_my_weekly_estimated.csv"
)


@lru_cache(maxsize=8)
def load_palm_oil() -> pd.DataFrame:
    """读取棕榈油 CPO=F 日线，列：Date, Open, High, Low, Close, Adj Close, Volume。"""
    if not os.path.exists(PALM_CSV):
        raise FileNotFoundError(f"Palm oil CSV not found: {PALM_CSV}")
    df = pd.read_csv(PALM_CSV, parse_dates=["Date"])
    df = df.dropna(subset=["Close"]).sort_values("Date").reset_index(drop=True)
    return df


@lru_cache(maxsize=8)
def load_prcp_oni_merged() -> pd.DataFrame:
    """读取 Day4 输出的月度合并表，列：DATE, PRCP, STATION_COUNT, ONI_Value。"""
    if not os.path.exists(PRCP_ONI_CSV):
        raise FileNotFoundError(f"prcp_oni_merged not found: {PRCP_ONI_CSV}")
    df = pd.read_csv(PRCP_ONI_CSV)
    return df


@lru_cache(maxsize=8)
def load_palm_oil_production() -> pd.DataFrame:
    """读取周度估算的马来西亚毛棕榈油产量，单位：吨。"""
    if not os.path.exists(PALM_PRODUCTION_CSV):
        raise FileNotFoundError(f"palm oil production CSV not found: {PALM_PRODUCTION_CSV}")
    df = pd.read_csv(PALM_PRODUCTION_CSV, parse_dates=["WEEK_START", "WEEK_END"])
    df["CPO_PRODUCTION_TONNES_WEEKLY_EST"] = pd.to_numeric(
        df["CPO_PRODUCTION_TONNES_WEEKLY_EST"], errors="coerce"
    )
    df = df.dropna(subset=["WEEK_START", "WEEK_END", "CPO_PRODUCTION_TONNES_WEEKLY_EST"])
    return df.sort_values("WEEK_START").reset_index(drop=True)


@lru_cache(maxsize=8)
def load_oni_monthly() -> pd.DataFrame:
    """读取 NOAA Niño 3.4 月度 ONI 长表，列：DATE (YYYY-MM), ONI_Value。"""
    if not os.path.exists(ONI_LONG_CSV):
        raise FileNotFoundError(f"ONI monthly CSV not found: {ONI_LONG_CSV}")
    df = pd.read_csv(ONI_LONG_CSV)
    df["ONI_Value"] = pd.to_numeric(df["ONI_Value"], errors="coerce")
    df = df.dropna(subset=["DATE", "ONI_Value"])
    return df.reset_index(drop=True)


def palm_with_oni(
    start: Optional[str] = None, end: Optional[str] = None
) -> list[dict]:
    """返回 [{date, close, oni}, ...]，把日频价格按「年-月」对齐到月度 ONI。

    ONI 是月度指标，价格是日度；同一个月内的所有交易日共享该月 ONI 值。
    某些月份若 ONI 尚未发布（如当前月），该日的 oni 取 None，前端做兜底。
    """
    df = load_palm_oil().copy()
    if start:
        df = df[df["Date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["Date"] <= pd.to_datetime(end)]

    oni = load_oni_monthly()
    oni_map = dict(zip(oni["DATE"], oni["ONI_Value"]))

    out = []
    for d, c in zip(df["Date"], df["Close"]):
        ym = d.strftime("%Y-%m")
        oni_val = oni_map.get(ym)
        out.append(
            {
                "date": d.strftime("%Y-%m-%d"),
                "close": float(c),
                "oni": float(oni_val) if oni_val is not None else None,
            }
        )
    return out


def palm_rows(start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
    """返回 [{date, close}, ...] 形式的行列表，供 /api/series 直接 JSON 化。

    日期统一格式 YYYY-MM-DD；Close 转成 Python float，避免 numpy 类型在 JSON 化时报错。
    """
    df = load_palm_oil()
    if start:
        df = df[df["Date"] >= pd.to_datetime(start)]
    if end:
        df = df[df["Date"] <= pd.to_datetime(end)]
    out = [
        {"date": d.strftime("%Y-%m-%d"), "close": float(c)}
        for d, c in zip(df["Date"], df["Close"])
    ]
    return out


def palm_summary() -> dict:
    """棕榈油数据元信息，供前端在加载时显示数据来源与跨度。"""
    df = load_palm_oil()
    return {
        "rows": int(len(df)),
        "start": df["Date"].min().strftime("%Y-%m-%d"),
        "end": df["Date"].max().strftime("%Y-%m-%d"),
        "missing_close": int(df["Close"].isna().sum()),
    }
