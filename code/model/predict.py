# -*- coding: utf-8 -*-
"""网站产量预测引擎：M2 三维模型 + ECMWF 情景预测。

职责:
  - 优先加载 code/model/model3d_weights.json (M2_spatial);
    若文件不存在, 才回退旧版 model_weights.json。
  - 构造目标月输入: ONI_lag12 + PRCP_DEV_3m + TAVG_DEV_10m + INTX_West_10m。
  - 历史月份优先读取 palm_oil_features.csv 中已生成的三维模型特征。
  - 未来月份优先用 ECMWF 季节预测; 缺失月份回退历史同期常态 (距平=0)。
  - ECMWF 网格同步聚合全国气候与西马气候, 用于西马温度×降水交互项。
  - 输出预测单产、还原绝对产量吨数, 以及逐因子贡献和数据来源。

这是后端真正算数的模块, DeepSeek 只负责对本模块的结构化结果做文字解释。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

# 允许后端从其他目录导入本模块时, 仍能找到同目录的 data_pipeline。
_MODEL_DIR = Path(__file__).resolve().parent
if str(_MODEL_DIR) not in sys.path:
    sys.path.insert(0, str(_MODEL_DIR))

import data_pipeline


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = Path(__file__).resolve().parent
MODEL3D_WEIGHTS_JSON = MODEL_DIR / "model3d_weights.json"
LEGACY_WEIGHTS_JSON = MODEL_DIR / "model_weights.json"
WEIGHTS_JSON = MODEL3D_WEIGHTS_JSON if MODEL3D_WEIGHTS_JSON.exists() else LEGACY_WEIGHTS_JSON
CLIMATE_XLSX = data_pipeline.CLIMATE_XLSX
FORECAST_SHEET = "04_MY_Climate_Forecast"
FEATURES_CSV = PROJECT_ROOT / "data" / "processed" / "product" / "palm_oil_features.csv"
REGIONAL_WEATHER_CSV = PROJECT_ROOT / "data" / "processed" / "meteo" / "malaysia_regional_weather_monthly.csv"

WEATHER_SOURCE_ECMWF = "ecmwf_seasonal_forecast"
WEATHER_SOURCE_BASELINE = "seasonal_climatology_baseline"
WEATHER_SOURCE_HISTORY = "observed_history"
WEST_BOX = (99.5, 104.75, 1.0, 7.0)  # lon_min, lon_max, lat_min, lat_max


def load_weights(path: Optional[Path] = None) -> dict:
    """读取模型权重, 校验关键字段齐全。"""
    path = path or WEIGHTS_JSON
    if not path.exists():
        raise FileNotFoundError(
            f"找不到模型权重 {path}, 请先运行 build_3factor_model.py 或 train_model.py"
        )
    weights = json.loads(path.read_text(encoding="utf-8"))
    for key in ("intercept", "coef"):
        if key not in weights:
            raise ValueError(f"{path.name} 缺少必要字段: {key}")
    return weights


def _selected_lags(weights: dict) -> Dict[str, int]:
    """从权重里取出三类变量的领先期 (整数月)。"""
    raw = weights.get("selected_lags", {})
    return {
        "ONI": int(raw.get("ONI", 12)),
        "PRCP_DEV_3m": int(raw.get("PRCP_DEV_3m", 0)),
        "TAVG_DEV_3m": int(raw.get("TAVG_DEV_3m", 0)),
    }


def _coef_keys(lags: Dict[str, int]) -> Dict[str, str]:
    """根据领先期拼出 coef 字典里的实际键名。"""
    return {
        "ONI": f"ONI_lag{lags['ONI']}",
        "PRCP": f"PRCP_DEV_3m_lag{lags['PRCP_DEV_3m']}",
        "TAVG": f"TAVG_DEV_3m_lag{lags['TAVG_DEV_3m']}",
    }


def _month_str(period: pd.Period) -> str:
    return str(period)


def _normalize_month(value: str) -> str:
    """把 2026-7 / 2026-07 统一成 YYYY-MM。"""
    return str(pd.Period(value, freq="M"))


def _shift_month(target_month: str, months: int) -> str:
    """把 YYYY-MM 往前/后移动 months 个月。"""
    base = pd.Period(_normalize_month(target_month), freq="M")
    return _month_str(base + months)


def _safe_float_map(df: pd.DataFrame, key_col: str, value_col: str) -> Dict[str, float]:
    if value_col not in df.columns:
        return {}
    tmp = df[[key_col, value_col]].dropna(subset=[key_col, value_col]).copy()
    tmp[value_col] = pd.to_numeric(tmp[value_col], errors="coerce")
    tmp = tmp.dropna(subset=[value_col])
    return {str(row[key_col])[:7]: float(row[value_col]) for _, row in tmp.iterrows()}


def _load_feature_history() -> dict:
    """读取研究阶段生成的特征表, 为网站提供最新三维模型历史特征。"""
    if not FEATURES_CSV.exists():
        return {"features": {}, "area_by_month": {}, "latest_area": None}
    df = pd.read_csv(FEATURES_CSV)
    df["Date"] = df["Date"].astype(str).str.slice(0, 7)
    features = {
        name: _safe_float_map(df, "Date", name)
        for name in [
            "PRCP_DEV",
            "TAVG_DEV",
            "PRCP_DEV_3m",
            "TAVG_DEV_10m",
            "T2M_DEV_West",
            "PRCP_DEV_West",
            "T2M_DEV_West_10m",
            "PRCP_DEV_West_10m",
            "INTX_West_10m",
        ]
    }
    area_by_month = _safe_float_map(df, "Date", "Mature_Area")
    latest_area = None
    if area_by_month:
        latest_month = sorted(area_by_month)[-1]
        latest_area = {"month": latest_month, "mature_area": area_by_month[latest_month]}
    return {"features": features, "area_by_month": area_by_month, "latest_area": latest_area}


def _load_west_climatology() -> Dict[int, Dict[str, float]]:
    """读取西马区域同月气候常态, 用于 ECMWF 西马交互项。"""
    if not REGIONAL_WEATHER_CSV.exists():
        return {}
    df = pd.read_csv(REGIONAL_WEATHER_CSV)
    west = df[df["Region"] == "West"].copy()
    if west.empty:
        return {}
    west["Month"] = pd.to_datetime(west["Date"]).dt.month
    clim = (
        west.groupby("Month", as_index=False)
        .agg(T2M_CLIM=("T2M_CLIM", "first"), PRCP_CLIM=("PRCP_CLIM", "first"))
    )
    return {
        int(row.Month): {"tavg_clim": float(row.T2M_CLIM), "prcp_clim": float(row.PRCP_CLIM)}
        for row in clim.itertuples(index=False)
    }


def load_climate_context() -> dict:
    """构建预测所需的气候上下文: 历史距平时间轴、同月常态、ONI 历史、ECMWF 预测。"""
    raw_climate = data_pipeline.read_climate_history()
    timeline = data_pipeline.enrich_climate_timeline(raw_climate)
    feature_history = _load_feature_history()

    climatology = (
        timeline.dropna(subset=["PRCP_CLIM", "TAVG_CLIM"])
        .groupby("Month", as_index=False)
        .agg(PRCP_CLIM=("PRCP_CLIM", "first"), TAVG_CLIM=("TAVG_CLIM", "first"))
    )
    prcp_clim = dict(zip(climatology["Month"], climatology["PRCP_CLIM"]))
    tavg_clim = dict(zip(climatology["Month"], climatology["TAVG_CLIM"]))

    prcp_dev_hist = dict(zip(timeline["Date"], timeline["PRCP_DEV"]))
    tavg_dev_hist = dict(zip(timeline["Date"], timeline["TAVG_DEV"]))
    # 特征表包含补齐后的 2026-01..05 实测/日度聚合数据, 覆盖旧 Excel 的历史距平。
    prcp_dev_hist.update(feature_history["features"].get("PRCP_DEV", {}))
    tavg_dev_hist.update(feature_history["features"].get("TAVG_DEV", {}))

    oni_hist = (
        raw_climate.dropna(subset=["ONI"])[["Date", "ONI"]]
        .assign(Date=lambda d: d["Date"].astype(str).str.slice(0, 7))
    )
    oni_map = dict(zip(oni_hist["Date"], oni_hist["ONI"]))

    forecast = _load_ecmwf_forecast()

    return {
        "timeline": timeline,
        "prcp_clim": prcp_clim,
        "tavg_clim": tavg_clim,
        "prcp_dev_hist": {k: v for k, v in prcp_dev_hist.items() if pd.notna(v)},
        "tavg_dev_hist": {k: v for k, v in tavg_dev_hist.items() if pd.notna(v)},
        "feature_history": feature_history["features"],
        "area_by_month": feature_history["area_by_month"],
        "latest_feature_area": feature_history["latest_area"],
        "west_climatology": _load_west_climatology(),
        "oni_map": oni_map,
        "forecast": forecast,
    }


def _load_ecmwf_forecast(path: Path = CLIMATE_XLSX) -> Dict[str, Dict[str, float]]:
    """读取 04_MY_Climate_Forecast 网格长表, 聚合全国与西马预测均值。"""
    try:
        grid = pd.read_excel(path, sheet_name=FORECAST_SHEET)
    except ValueError:
        return {}
    required = {"TARGET_YM", "T2M_C", "PRCP_MM_PER_MONTH"}
    if not required.issubset(grid.columns):
        return {}

    grid = grid.dropna(subset=["TARGET_YM", "T2M_C", "PRCP_MM_PER_MONTH"]).copy()
    grid["TARGET_YM"] = grid["TARGET_YM"].astype(str).str.slice(0, 7)
    grid["T2M_C"] = pd.to_numeric(grid["T2M_C"], errors="coerce")
    grid["PRCP_MM_PER_MONTH"] = pd.to_numeric(grid["PRCP_MM_PER_MONTH"], errors="coerce")
    grid = grid.dropna(subset=["T2M_C", "PRCP_MM_PER_MONTH"])

    aggregated = (
        grid.groupby("TARGET_YM", as_index=False)
        .agg(
            T2M_C=("T2M_C", "mean"),
            PRCP_MM_PER_MONTH=("PRCP_MM_PER_MONTH", "mean"),
            GRID_ROWS=("T2M_C", "count"),
        )
    )
    result = {
        row.TARGET_YM: {
            "T2M_C": float(row.T2M_C),
            "PRCP_MM_PER_MONTH": float(row.PRCP_MM_PER_MONTH),
            "grid_rows": int(row.GRID_ROWS),
        }
        for row in aggregated.itertuples(index=False)
    }

    if {"LAT", "LON"}.issubset(grid.columns):
        lo, hi, la, ha = WEST_BOX
        west = grid[
            (grid["LON"] >= lo)
            & (grid["LON"] <= hi)
            & (grid["LAT"] >= la)
            & (grid["LAT"] <= ha)
        ].copy()
        try:
            from global_land_mask import globe

            west = west[[bool(globe.is_land(lat, lon)) for lat, lon in zip(west["LAT"], west["LON"])]]
        except Exception:
            # 陆地掩膜不可用时保留经纬度框均值, 不阻断网站预测。
            pass
        if not west.empty:
            west_agg = (
                west.groupby("TARGET_YM", as_index=False)
                .agg(
                    WEST_T2M_C=("T2M_C", "mean"),
                    WEST_PRCP_MM_PER_MONTH=("PRCP_MM_PER_MONTH", "mean"),
                    WEST_GRID_ROWS=("T2M_C", "count"),
                )
            )
            for row in west_agg.itertuples(index=False):
                result.setdefault(row.TARGET_YM, {})
                result[row.TARGET_YM].update(
                    {
                        "WEST_T2M_C": float(row.WEST_T2M_C),
                        "WEST_PRCP_MM_PER_MONTH": float(row.WEST_PRCP_MM_PER_MONTH),
                        "west_grid_rows": int(row.WEST_GRID_ROWS),
                    }
                )
    return result


def _month_deviation(
    month: str,
    context: dict,
) -> Dict[str, object]:
    """取某个月的降水/气温距平, 标注来源 (历史实测 / ECMWF / 基准)。

    优先级: 历史实测 > ECMWF 预测 > 基准 (距平=0)。
    """
    calendar_month = pd.Period(month, freq="M").month
    prcp_clim = context["prcp_clim"].get(calendar_month)
    tavg_clim = context["tavg_clim"].get(calendar_month)

    if month in context["prcp_dev_hist"] and month in context["tavg_dev_hist"]:
        return {
            "month": month,
            "prcp_dev": float(context["prcp_dev_hist"][month]),
            "tavg_dev": float(context["tavg_dev_hist"][month]),
            "source": WEATHER_SOURCE_HISTORY,
        }

    forecast = context["forecast"].get(month)
    if forecast is not None and prcp_clim is not None and tavg_clim is not None:
        return {
            "month": month,
            "prcp_dev": float(forecast["PRCP_MM_PER_MONTH"] - prcp_clim),
            "tavg_dev": float(forecast["T2M_C"] - tavg_clim),
            "source": WEATHER_SOURCE_ECMWF,
        }

    return {
        "month": month,
        "prcp_dev": 0.0,
        "tavg_dev": 0.0,
        "source": WEATHER_SOURCE_BASELINE,
    }


def _west_month_deviation(month: str, context: dict) -> Dict[str, object]:
    """取西马某月温度/降水距平, 支持历史特征、ECMWF 西马格点、基准回退。"""
    feature = context.get("feature_history", {})
    west_t_hist = feature.get("T2M_DEV_West", {})
    west_p_hist = feature.get("PRCP_DEV_West", {})
    if month in west_t_hist and month in west_p_hist:
        return {
            "month": month,
            "west_tavg_dev": float(west_t_hist[month]),
            "west_prcp_dev": float(west_p_hist[month]),
            "source": WEATHER_SOURCE_HISTORY,
        }

    calendar_month = pd.Period(month, freq="M").month
    forecast = context.get("forecast", {}).get(month)
    clim = context.get("west_climatology", {}).get(calendar_month)
    if forecast is not None and clim is not None and "WEST_T2M_C" in forecast and "WEST_PRCP_MM_PER_MONTH" in forecast:
        return {
            "month": month,
            "west_tavg_dev": float(forecast["WEST_T2M_C"] - clim["tavg_clim"]),
            "west_prcp_dev": float(forecast["WEST_PRCP_MM_PER_MONTH"] - clim["prcp_clim"]),
            "source": WEATHER_SOURCE_ECMWF,
        }

    return {
        "month": month,
        "west_tavg_dev": 0.0,
        "west_prcp_dev": 0.0,
        "source": WEATHER_SOURCE_BASELINE,
    }


def _rolling_3m_deviation(target_month: str, context: dict) -> Dict[str, object]:
    """计算目标月的 3 月滚动降水/气温距平 (目标月 + 前两个月)。"""
    months = [_shift_month(target_month, -offset) for offset in (2, 1, 0)]
    parts = [_month_deviation(m, context) for m in months]

    prcp_dev_3m = sum(p["prcp_dev"] for p in parts) / len(parts)
    tavg_dev_3m = sum(p["tavg_dev"] for p in parts) / len(parts)

    sources = {p["source"] for p in parts}
    if sources == {WEATHER_SOURCE_HISTORY}:
        overall = WEATHER_SOURCE_HISTORY
    elif WEATHER_SOURCE_ECMWF in sources:
        overall = (
            WEATHER_SOURCE_ECMWF
            if sources <= {WEATHER_SOURCE_ECMWF, WEATHER_SOURCE_HISTORY}
            else "ecmwf_with_baseline_fallback"
        )
    elif sources == {WEATHER_SOURCE_BASELINE}:
        overall = WEATHER_SOURCE_BASELINE
    else:
        overall = "mixed_history_and_baseline"

    return {
        "prcp_dev_3m": float(prcp_dev_3m),
        "tavg_dev_3m": float(tavg_dev_3m),
        "window_months": months,
        "window_detail": parts,
        "weather_source": overall,
    }


def _rolling_model3d_features(target_month: str, context: dict) -> Dict[str, object]:
    """计算三维模型需要的 PRCP_DEV_3m / TAVG_DEV_10m / INTX_West_10m。"""
    feature = context.get("feature_history", {})
    hist_prcp3 = feature.get("PRCP_DEV_3m", {})
    hist_tavg10 = feature.get("TAVG_DEV_10m", {})
    hist_intx = feature.get("INTX_West_10m", {})

    if target_month in hist_prcp3 and target_month in hist_tavg10 and target_month in hist_intx:
        return {
            "prcp_dev_3m": float(hist_prcp3[target_month]),
            "tavg_dev_10m": float(hist_tavg10[target_month]),
            "intx_west_10m": float(hist_intx[target_month]),
            "window_months": [_shift_month(target_month, -offset) for offset in range(9, -1, -1)],
            "window_detail": [],
            "weather_source": WEATHER_SOURCE_HISTORY,
        }

    prcp_months = [_shift_month(target_month, -offset) for offset in (2, 1, 0)]
    temp_months = [_shift_month(target_month, -offset) for offset in range(9, -1, -1)]
    nat_parts = [_month_deviation(m, context) for m in temp_months]
    west_parts = [_west_month_deviation(m, context) for m in temp_months]

    prcp_lookup = {p["month"]: p for p in nat_parts}
    prcp_dev_3m = sum(prcp_lookup[m]["prcp_dev"] for m in prcp_months) / len(prcp_months)
    tavg_dev_10m = sum(p["tavg_dev"] for p in nat_parts) / len(nat_parts)
    west_tavg_10m = sum(p["west_tavg_dev"] for p in west_parts) / len(west_parts)
    west_prcp_10m = sum(p["west_prcp_dev"] for p in west_parts) / len(west_parts)
    intx_west_10m = west_tavg_10m * west_prcp_10m

    details = []
    for nat, west in zip(nat_parts, west_parts):
        details.append(
            {
                "month": nat["month"],
                "prcp_dev": float(nat["prcp_dev"]),
                "tavg_dev": float(nat["tavg_dev"]),
                "west_tavg_dev": float(west["west_tavg_dev"]),
                "west_prcp_dev": float(west["west_prcp_dev"]),
                "source": nat["source"] if nat["source"] == west["source"] else "mixed_national_and_west",
            }
        )

    sources = {p["source"] for p in details}
    if sources == {WEATHER_SOURCE_HISTORY}:
        overall = WEATHER_SOURCE_HISTORY
    elif WEATHER_SOURCE_ECMWF in sources or "mixed_national_and_west" in sources:
        overall = WEATHER_SOURCE_ECMWF if WEATHER_SOURCE_BASELINE not in sources else "ecmwf_with_baseline_fallback"
    elif sources == {WEATHER_SOURCE_BASELINE}:
        overall = WEATHER_SOURCE_BASELINE
    else:
        overall = "mixed_history_and_baseline"

    return {
        "prcp_dev_3m": float(prcp_dev_3m),
        "tavg_dev_10m": float(tavg_dev_10m),
        "intx_west_10m": float(intx_west_10m),
        "west_tavg_dev_10m": float(west_tavg_10m),
        "west_prcp_dev_10m": float(west_prcp_10m),
        "window_months": temp_months,
        "prcp_window_months": prcp_months,
        "window_detail": details,
        "weather_source": overall,
    }


def _current_real_month() -> str:
    """当前现实月份 YYYY-MM。"""
    from datetime import date
    today = date.today()
    return f"{today.year:04d}-{today.month:02d}"


def _forecast_meta(context: dict) -> Dict[str, object]:
    """从已加载的 ECMWF 上下文中提取起报月和覆盖范围。"""
    forecast = context.get("forecast", {})
    if not forecast:
        return {
            "reference_month": None,
            "coverage": [],
            "coverage_start": None,
            "coverage_end": None,
        }
    coverage = sorted(forecast.keys())
    ref_date = coverage[0]
    try:
        grid_path = PROJECT_ROOT / "data" / "processed" / "meteo" / "ecmwf_seasonal_forecast_malaysia_grid.csv"
        if grid_path.exists():
            grid_csv = pd.read_csv(grid_path, usecols=["FORECAST_REFERENCE_TIME"], nrows=1)
            if not grid_csv.empty:
                ref_date = str(grid_csv["FORECAST_REFERENCE_TIME"].iloc[0])[:7]
    except Exception:
        pass
    return {
        "reference_month": ref_date,
        "coverage": coverage,
        "coverage_start": coverage[0] if coverage else None,
        "coverage_end": coverage[-1] if coverage else None,
    }


def _accuracy_info(target_month: str, rolling: Dict[str, object], context: dict) -> Dict[str, object]:
    """动态精度：根据当前现实月份 + ECMWF 起报月 + 3 个月窗口覆盖度综合判定。"""
    if rolling.get("weather_source") == WEATHER_SOURCE_HISTORY:
        return {
            "level": "high",
            "label": "高精度",
            "message": "目标月气候特征来自历史实测/已聚合观测数据。",
            "current_month": _current_real_month(),
            "forecast_reference_month": None,
            "forecast_is_current": True,
            "needs_update": False,
            "forecast_coverage": [],
            "high_accuracy_range": [],
            "medium_accuracy_range": [],
            "ecmwf_months": [],
            "baseline_months": [],
            "history_months": rolling.get("window_months", []),
            "ecmwf_month_count": 0,
            "window_month_count": len(rolling.get("window_months", [])),
        }

    details = rolling.get("window_detail", [])
    ecmwf_months = [p["month"] for p in details if p.get("source") == WEATHER_SOURCE_ECMWF]
    baseline_months = [p["month"] for p in details if p.get("source") == WEATHER_SOURCE_BASELINE]
    history_months = [p["month"] for p in details if p.get("source") == WEATHER_SOURCE_HISTORY]
    ecmwf_count = len(ecmwf_months)

    current_month = _current_real_month()
    fm = _forecast_meta(context)
    ref_month = fm["reference_month"]
    coverage = fm["coverage"]

    forecast_is_current = (ref_month == current_month) if ref_month else False

    target_detail = next((p for p in details if p.get("month") == target_month), None)
    target_source = target_detail.get("source") if target_detail else WEATHER_SOURCE_BASELINE

    needs_update = not forecast_is_current

    if target_source == WEATHER_SOURCE_BASELINE:
        level = "low"
        label = "低精度"
        if needs_update:
            message = "当前 ECMWF 文件不是本月起报，且目标月无预报覆盖。请更新气候预测文件。"
        else:
            message = "当前月份缺少 ECMWF 天气预报，结果为基准预测，准确性较低。请更新气候预测文件。"
    elif not forecast_is_current:
        level = "medium"
        label = "中等精度"
        message = "ECMWF 文件非本月起报，预报可能已过期。建议更新气候预测文件。"
    elif ecmwf_count == 3:
        level = "high"
        label = "高精度"
        message = "完整 ECMWF 3 个月滚动天气窗口，起报月为当前现实月份。"
    elif ecmwf_count in {1, 2}:
        level = "medium"
        label = "中等精度"
        message = "部分月份用 ECMWF，缺失月份用历史同期常态补齐。"
    else:
        level = "low"
        label = "低精度"
        message = "当前月份缺少 ECMWF 天气预报，结果为基准预测，准确性较低。请更新气候预测文件。"

    high_range = []
    medium_range = []
    if coverage and forecast_is_current:
        for ym in coverage:
            window = [_shift_month(ym, -offset) for offset in (2, 1, 0)]
            if all(m in coverage or m in context.get("prcp_dev_hist", {}) for m in window):
                all_ecmwf = all(m in coverage for m in window)
                if all_ecmwf:
                    high_range.append(ym)
                else:
                    medium_range.append(ym)
            else:
                medium_range.append(ym)

    return {
        "level": level,
        "label": label,
        "message": message,
        "current_month": current_month,
        "forecast_reference_month": ref_month,
        "forecast_is_current": forecast_is_current,
        "needs_update": needs_update,
        "forecast_coverage": coverage,
        "high_accuracy_range": high_range,
        "medium_accuracy_range": medium_range,
        "ecmwf_months": ecmwf_months,
        "baseline_months": baseline_months,
        "history_months": history_months,
        "ecmwf_month_count": ecmwf_count,
        "window_month_count": len(details),
    }


def _latest_mature_area() -> Dict[str, float]:
    """取 MPOB 最新一年的成熟面积, 用于旧数据兜底。"""
    area = data_pipeline.read_area_monthly()
    area = area.copy()
    area["Year"] = area["Date"].str.slice(0, 4).astype(int)
    latest_year = int(area["Year"].max())
    latest = area[area["Year"] == latest_year].iloc[0]
    return {"year": latest_year, "mature_area": float(latest["Mature_Area"])}


def _mature_area_for_month(target_month: str, context: dict) -> Dict[str, float]:
    """按目标月取成熟面积; 若当月缺失, 使用同年/最新特征面积兜底。"""
    area_by_month = context.get("area_by_month", {}) or {}
    if target_month in area_by_month:
        return {
            "year": int(target_month[:4]),
            "mature_area": float(area_by_month[target_month]),
            "source": "model_feature_area",
        }
    target_year = target_month[:4]
    same_year = sorted(k for k in area_by_month if k.startswith(target_year))
    if same_year:
        month = same_year[-1]
        return {
            "year": int(target_year),
            "mature_area": float(area_by_month[month]),
            "source": f"model_feature_area_latest_{month}",
        }
    latest = context.get("latest_feature_area")
    if latest:
        return {
            "year": int(latest["month"][:4]),
            "mature_area": float(latest["mature_area"]),
            "source": f"model_feature_area_latest_{latest['month']}",
        }
    legacy = _latest_mature_area()
    legacy["source"] = "mpob_latest_area"
    return legacy


def predict_future_production(
    target_month: str,
    weights: Optional[dict] = None,
    context: Optional[dict] = None,
) -> dict:
    """预测目标月 (YYYY-MM) 的棕榈油单产与绝对产量吨数, 返回逐因子贡献。"""
    target_month = _normalize_month(target_month)

    weights = weights or load_weights()
    context = context or load_climate_context()

    lags = _selected_lags(weights)
    coef_keys = _coef_keys(lags)
    coef = weights["coef"]
    intercept = float(weights["intercept"])
    use_model3d = "TAVG_DEV_10m" in coef or "INTX_West_10m" in coef

    oni_month = _shift_month(target_month, -lags["ONI"])
    oni_value = context["oni_map"].get(oni_month)
    oni_source = "observed" if oni_value is not None else "fallback_zero"
    if oni_value is None:
        oni_value = 0.0

    rolling = _rolling_model3d_features(target_month, context) if use_model3d else _rolling_3m_deviation(target_month, context)
    accuracy = _accuracy_info(target_month, rolling, context)
    prcp_dev_3m = rolling["prcp_dev_3m"]
    tavg_feature_value = rolling["tavg_dev_10m"] if use_model3d else rolling["tavg_dev_3m"]
    intx_west_10m = float(rolling.get("intx_west_10m", 0.0))

    trend_index = int(
        (pd.Period(target_month, freq="M") - pd.Period(data_pipeline.TREND_BASELINE_YM, freq="M")).n
    )
    calendar_month = pd.Period(target_month, freq="M").month
    month_key = f"month_{calendar_month}"

    beta_trend = float(coef.get("Trend", 0.0))
    beta_oni = float(coef.get(coef_keys["ONI"], 0.0))
    beta_prcp = float(coef.get("PRCP_DEV_3m", coef.get(coef_keys["PRCP"], 0.0)))
    beta_tavg = float(coef.get("TAVG_DEV_10m", coef.get(coef_keys["TAVG"], 0.0)))
    beta_intx_west = float(coef.get("INTX_West_10m", 0.0))
    month_coef = float(coef.get(month_key, 0.0))

    contrib_trend = beta_trend * trend_index
    contrib_oni = beta_oni * float(oni_value)
    contrib_prcp = beta_prcp * prcp_dev_3m
    contrib_tavg = beta_tavg * tavg_feature_value
    contrib_intx_west = beta_intx_west * intx_west_10m
    contrib_month = month_coef

    yield_pred = (
        intercept
        + contrib_trend
        + contrib_oni
        + contrib_prcp
        + contrib_tavg
        + contrib_intx_west
        + contrib_month
    )

    area_info = _mature_area_for_month(target_month, context)
    production_pred = yield_pred * area_info["mature_area"]

    return {
        "target_month": target_month,
        "predicted_yield": float(yield_pred),
        "predicted_production_tonnes": float(production_pred),
        "mature_area_hectares": area_info["mature_area"],
        "mature_area_year": area_info["year"],
        "weather_source": rolling["weather_source"],
        "accuracy": accuracy,
        "inputs": {
            "oni_lag_months": lags["ONI"],
            "oni_reference_month": oni_month,
            "oni_value": float(oni_value),
            "oni_source": oni_source,
            "prcp_dev_3m": prcp_dev_3m,
            "tavg_dev_3m": rolling.get("tavg_dev_3m"),
            "tavg_dev_10m": rolling.get("tavg_dev_10m"),
            "intx_west_10m": intx_west_10m,
            "west_tavg_dev_10m": rolling.get("west_tavg_dev_10m"),
            "west_prcp_dev_10m": rolling.get("west_prcp_dev_10m"),
            "rolling_window_months": rolling["window_months"],
            "prcp_window_months": rolling.get("prcp_window_months", rolling["window_months"]),
            "rolling_window_detail": rolling["window_detail"],
            "trend_index": trend_index,
            "calendar_month": calendar_month,
        },
        "contributions": {
            "intercept": intercept,
            "trend": float(contrib_trend),
            "ONI": float(contrib_oni),
            "PRCP": float(contrib_prcp),
            "TAVG": float(contrib_tavg),
            "INTX_West": float(contrib_intx_west),
            "seasonality": float(contrib_month),
        },
        "model": {
            "model_name": weights.get("model_name", "legacy_model"),
            "features": weights.get("features"),
            "selected_lags": lags,
            "trained_window": weights.get("trained_window"),
            "metrics": weights.get("metrics"),
            "area_source": area_info.get("source"),
        },
    }


def predict_range(start_month: str, n_months: int = 12) -> List[dict]:
    """连续预测从 start_month 起的 n_months 个月, 供网站 12 个月预测使用。"""
    if n_months < 1:
        raise ValueError("n_months 必须 >= 1")
    start_month = _normalize_month(start_month)
    weights = load_weights()
    context = load_climate_context()
    return [
        predict_future_production(_shift_month(start_month, i), weights=weights, context=context)
        for i in range(n_months)
    ]


def main() -> None:
    weights = load_weights()
    context = load_climate_context()

    forecast_months = sorted(context["forecast"].keys())
    print(f"[weights] selected_lags={_selected_lags(weights)}")
    print(f"[ecmwf] forecast months in archive: {forecast_months or '无'}")

    demo_months = []
    if forecast_months:
        demo_months.append(forecast_months[0])
    demo_months.append(_shift_month("2026-05", 1))  # 2026-06, 紧邻历史末端的基准月

    for month in demo_months:
        result = predict_future_production(month, weights=weights, context=context)
        print(
            f"\n[predict {month}] yield={result['predicted_yield']:.5f} t/ha "
            f"production={result['predicted_production_tonnes']:.0f} t "
            f"weather_source={result['weather_source']}"
        )
        contrib = result["contributions"]
        print(
            "  contributions: "
            + ", ".join(f"{k}={v:.5f}" for k, v in contrib.items())
        )
        inputs = result["inputs"]
        tavg_label = "TAVG_DEV_10m" if inputs.get("tavg_dev_10m") is not None else "TAVG_DEV_3m"
        tavg_value = inputs.get("tavg_dev_10m")
        if tavg_value is None:
            tavg_value = inputs.get("tavg_dev_3m", 0.0)
        print(
            f"  inputs: ONI({inputs['oni_reference_month']})={inputs['oni_value']:.3f}[{inputs['oni_source']}], "
            f"PRCP_DEV_3m={inputs['prcp_dev_3m']:.3f}, {tavg_label}={float(tavg_value):.3f}, "
            f"INTX_West_10m={float(inputs.get('intx_west_10m', 0.0)):.3f}"
        )
        for part in inputs["rolling_window_detail"]:
            print(
                f"    {part['month']}: prcp_dev={part['prcp_dev']:.3f}, "
                f"tavg_dev={part['tavg_dev']:.3f}, source={part['source']}"
            )


if __name__ == "__main__":
    main()
