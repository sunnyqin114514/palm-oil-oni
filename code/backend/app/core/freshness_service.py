"""数据新鲜度检测服务 (data freshness service)。

根据当前实际日期，自动检测各数据源可用状态，
判定当年预测是否就绪、下一年预测需要补充什么数据。
"""

from __future__ import annotations

import os
from datetime import date, datetime
from functools import lru_cache
from typing import Any, Dict, List

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(HERE))
CODE_DIR = os.path.dirname(BACKEND_DIR)
DATA_DIR = os.path.join(CODE_DIR, "..", "data")
MODEL_DIR = os.path.join(CODE_DIR, "model")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")

SOURCES = [
    {
        "id": "oni",
        "name": "ONI (NOAA)",
        "description": "Oceanic Niño Index 月度数据",
        "url": "https://origin.cpc.ncep.noaa.gov/products/analysis_monitoring/ensostuff/ONI_v5.php",
        "freq": "monthly",
    },
    {
        "id": "weather",
        "name": "NASA POWER 气温/降水",
        "description": "马来西亚区域栅格天气月度数据",
        "url": "https://power.larc.nasa.gov/data-access-viewer/",
        "freq": "monthly",
    },
    {
        "id": "production",
        "name": "MPOB 棕榈油产量",
        "description": "马来西亚月度棕榈油产量",
        "url": "https://bepi.mpob.gov.my/",
        "freq": "monthly",
    },
    {
        "id": "area",
        "name": "MPOB 成熟种植面积",
        "description": "马来西亚棕榈油成熟种植面积（年度）",
        "url": "https://bepi.mpob.gov.my/",
        "freq": "yearly",
    },
    {
        "id": "ecmwf",
        "name": "ECMWF 季节预报",
        "description": "未来 6 个月气温/降水集合预报",
        "url": "https://cds.climate.copernicus.eu/datasets/seasonal-monthly-single-levels?tab=download",
        "freq": "on_demand",
    },
]


def _detect_oni_latest() -> str | None:
    """检测 ONI 数据最新可用月份。"""
    oni_path = os.path.join(DATA_DIR, "processed", "meteo", "noaa_nino34_pacific_oni_monthly.csv")
    if not os.path.exists(oni_path):
        return None
    try:
        df = pd.read_csv(oni_path)
        if "Date" in df.columns:
            last = df["Date"].dropna().iloc[-1]
            return str(last)[:7]
    except Exception:
        pass
    return None


def _detect_weather_latest() -> str | None:
    """检测 NASA POWER 天气数据最新月份（通过 features CSV 判断）。"""
    feat_path = os.path.join(DATA_DIR, "processed", "product", "palm_oil_features.csv")
    if not os.path.exists(feat_path):
        return None
    try:
        df = pd.read_csv(feat_path, usecols=["Date"])
        last = df["Date"].dropna().iloc[-1]
        return str(last)[:7]
    except Exception:
        return None


def _detect_production_latest() -> str | None:
    """检测 MPOB 产量数据最新月份。"""
    prod_path = os.path.join(DATA_DIR, "processed", "product", "palm_oil_production_my_monthly.csv")
    if not os.path.exists(prod_path):
        return None
    try:
        df = pd.read_csv(prod_path)
        if "DATE" in df.columns:
            last = df["DATE"].dropna().iloc[-1]
            return str(last)[:7]
    except Exception:
        pass
    return None


def _detect_area_latest() -> str | None:
    """检测成熟面积数据最新年份。"""
    area_path = os.path.join(DATA_DIR, "raw", "product", "mpob_palm_oil_planted_area_mature.csv")
    if not os.path.exists(area_path):
        return None
    try:
        df = pd.read_csv(area_path)
        if "YEAR" in df.columns:
            return str(int(df["YEAR"].dropna().max()))
    except Exception:
        pass
    return None


def _detect_ecmwf_latest() -> str | None:
    """检测 ECMWF 预报文件最新参考日期。"""
    ecmwf_dir = os.path.join(DATA_DIR, "raw", "meteo")
    if not os.path.isdir(ecmwf_dir):
        return None
    try:
        files = [f for f in os.listdir(ecmwf_dir) if "ecmwf" in f.lower() and f.endswith(".nc")]
        if not files:
            return None
        import re
        dates = []
        for f in files:
            m = re.search(r"(\d{6})", f)
            if m:
                d = m.group(1)
                dates.append(d[:4] + "-" + d[4:6])
        return max(dates) if dates else None
    except Exception:
        return None


def get_data_freshness() -> Dict[str, Any]:
    """返回数据新鲜度检测结果。"""
    today = date.today()
    current_year = today.year
    next_year = current_year + 1
    current_month = today.month

    detectors = {
        "oni": _detect_oni_latest,
        "weather": _detect_weather_latest,
        "production": _detect_production_latest,
        "area": _detect_area_latest,
        "ecmwf": _detect_ecmwf_latest,
    }

    results: List[Dict[str, Any]] = []

    for src in SOURCES:
        sid = src["id"]
        latest = detectors[sid]()

        if sid == "area":
            ready_current = latest is not None and int(latest) >= current_year - 1
            needed_next = f"{current_year} 年度面积数据（通常次年 3 月发布）"
        elif sid == "ecmwf":
            ready_current = latest is not None
            needed_next = f"起报日期覆盖 {next_year} 年的季节预报 .nc 文件"
        else:
            if latest:
                latest_y, latest_m = int(latest[:4]), int(latest[5:7])
                ready_current = latest_y >= current_year and latest_m >= current_month - 2
                needed_next = f"{current_year}-01 至 {current_year}-12 完整 12 个月数据"
            else:
                ready_current = False
                needed_next = f"{current_year} 全年数据（当前未检测到数据文件）"

        results.append({
            "id": sid,
            "name": src["name"],
            "description": src["description"],
            "url": src["url"],
            "latest_available": latest or "未检测到",
            "ready_for_current_year": ready_current,
            "needed_for_next_year": needed_next,
        })

    all_ready = all(r["ready_for_current_year"] for r in results)

    return {
        "check_date": today.isoformat(),
        "current_year": current_year,
        "next_year": next_year,
        "current_year_ready": all_ready,
        "sources": results,
        "next_year_instructions": (
            f"要预测 {next_year} 年产量，需要将 {current_year} 年全年数据更新到系统中。"
            f"具体步骤：① 等待 {current_year} 年 12 月数据发布（通常次月可得）；"
            f"② 从各来源下载最新数据并替换/追加到 data/ 目录；"
            f"③ 重新运行 feature_builder.py 生成特征；"
            f"④ 上传最新 ECMWF 预报文件覆盖 {next_year} 年目标月份。"
        ),
        "lifecycle": {
            "train": "2010-01 → 2023-12（168 个月）",
            "validate": "2024-01 → 2026-05（28 个月）",
            "current": f"{current_year}-01 → {current_year}-12（预测中）",
            "next": f"{next_year}-01 → {next_year}-12（待数据更新）",
        },
    }
