"""单产历史与预测视界服务 (yield history & prediction horizon)。

为 3D 柱状图提供:
  - 历史同期(日历月)平均单产 -> 折线基线
  - 历史实测单产逐月值 -> 蓝色柱(已存在数据)
  - 预测视界 -> 最新 ONI 月份 + 12 个月领先期(动态), 限制未来年份的可显示范围
  - 实测/预测分界月 -> 2026 蓝/紫分界
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Dict

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(HERE))
CODE_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_DIR = os.path.dirname(CODE_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")

FEATURES_CSV = os.path.join(DATA_DIR, "processed", "product", "palm_oil_features.csv")
ONI_CSV = os.path.join(DATA_DIR, "processed", "meteo", "noaa_nino34_pacific_oni_monthly.csv")

ONI_LEAD_MONTHS = 12  # 模型 ONI_lag12: ONI 领先产量 12 个月, 这是唯一的长期领先信号


def _shift_month(ym: str, n: int) -> str:
    """把 'YYYY-MM' 平移 n 个月。"""
    period = pd.Period(ym, freq="M") + n
    return f"{period.year:04d}-{period.month:02d}"


@lru_cache(maxsize=1)
def _latest_oni_month() -> str | None:
    """读取 ONI 最新可用月份。"""
    if not os.path.exists(ONI_CSV):
        return None
    try:
        df = pd.read_csv(ONI_CSV)
        if "Date" in df.columns and len(df):
            return str(df["Date"].dropna().iloc[-1])[:7]
    except Exception:
        return None
    return None


@lru_cache(maxsize=1)
def load_yield_history() -> dict:
    """返回历史同期均值、实测逐月单产、预测视界。"""
    if not os.path.exists(FEATURES_CSV):
        raise FileNotFoundError(f"特征文件缺失: {FEATURES_CSV}")

    df = pd.read_csv(FEATURES_CSV, usecols=["Date", "Year", "Month", "Yield"])
    df = df.dropna(subset=["Yield"]).copy()
    df["Date"] = df["Date"].astype(str).str.slice(0, 7)

    # 历史同期(日历月)平均单产: 1~12 月各自的多年均值
    seasonal = df.groupby("Month")["Yield"].mean()
    seasonal_avg: Dict[str, float] = {
        str(int(m)): round(float(v), 6) for m, v in seasonal.items()
    }

    # 实测逐月单产 (已存在数据)
    actual: Dict[str, float] = {
        str(row.Date): round(float(row.Yield), 6) for row in df.itertuples(index=False)
    }

    latest_observed_month = df["Date"].iloc[-1] if len(df) else None

    # 预测视界: 最新 ONI 月份 + 12 个月领先期 (动态)
    latest_oni = _latest_oni_month()
    max_predict_month = _shift_month(latest_oni, ONI_LEAD_MONTHS) if latest_oni else None

    return {
        "seasonal_avg": seasonal_avg,
        "actual": actual,
        "latest_observed_month": latest_observed_month,
        "latest_oni_month": latest_oni,
        "lead_months": ONI_LEAD_MONTHS,
        "max_predict_month": max_predict_month,
        "history_start": df["Date"].iloc[0] if len(df) else None,
        "note": (
            f"历史同期均值基于 {df['Date'].iloc[0]}~{latest_observed_month} 实测单产; "
            f"领先期 = 最新 ONI 月份({latest_oni}) + {ONI_LEAD_MONTHS} 个月 = {max_predict_month}。"
        ),
    }


def clear_cache() -> None:
    _latest_oni_month.cache_clear()
    load_yield_history.cache_clear()
