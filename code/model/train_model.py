# -*- coding: utf-8 -*-
"""第二阶段：训练带季节项的多元线性回归并固化权重。

输入:
  data/processed/product/palm_oil_model_dataset.csv  (第一阶段 df_clean)

输出:
  code/model/model_weights.json
  code/model/yield_fit_actual_vs_pred.png
  code/model/yield_effect_ONI_lag12.png
  code/model/yield_effect_PRCP_DEV.png
  code/model/yield_effect_TAVG_DEV.png

要求:
  - 自变量: ONI_lag12 + PRCP_DEV + TAVG_DEV + 11 个月份哑变量 (1 月为基准)
  - statsmodels OLS, add_constant
  - 打印 summary, 保存系数与指标
  - 整体真实 vs 拟合 Yield 时间序列图
  - 三张逐自变量偏回归 / 边际效应图 (含拟合直线 + R^2 + p 值标注)
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.graphics.regressionplots import plot_partregress


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_CSV = PROJECT_ROOT / "data" / "processed" / "product" / "palm_oil_model_dataset.csv"
MODEL_DIR = Path(__file__).resolve().parent
WEIGHTS_JSON = MODEL_DIR / "model_weights.json"
FIT_PNG = MODEL_DIR / "yield_fit_actual_vs_pred.png"
TREND_PNG = MODEL_DIR / "yield_trend_decomposition.png"
EFFECT_PNGS = {
    "Trend": MODEL_DIR / "yield_effect_Trend.png",
    "ONI_lag12": MODEL_DIR / "yield_effect_ONI_lag12.png",
    "PRCP_DEV_3m": MODEL_DIR / "yield_effect_PRCP_DEV_3m.png",
    "TAVG_DEV_3m": MODEL_DIR / "yield_effect_TAVG_DEV_3m.png",
}

TREND_FEATURE = "Trend"
CLIMATE_FEATURES = ["ONI_lag12", "PRCP_DEV_3m", "TAVG_DEV_3m"]
REGRESSORS = [TREND_FEATURE, *CLIMATE_FEATURES]
BASELINE_MONTH = 1
MONTH_DUMMIES = [f"month_{m}" for m in range(2, 13)]


def load_dataset(path: Path = DATA_CSV) -> pd.DataFrame:
    """读取第一阶段 df_clean, 校验关键列。"""
    if not path.exists():
        raise FileNotFoundError(
            f"找不到第一阶段输出 {path}, 请先运行 code/model/data_pipeline.py"
        )
    df = pd.read_csv(path)
    required = ["Date", "Yield", *REGRESSORS, "Month"]
    missing = set(required).difference(df.columns)
    if missing:
        raise ValueError(f"df_clean 缺少必要字段: {sorted(missing)}")
    if df[required].isna().any().any():
        raise ValueError("df_clean 中关键字段存在缺失, 请检查第一阶段管线。")
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def build_design_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """构造 X: Trend + 三个气候变量 + 11 个月份哑变量, 1 月作为基准。"""
    X = df[REGRESSORS].copy()
    months = df["Month"].astype(int)
    for m in range(2, 13):
        X[f"month_{m}"] = (months == m).astype(int)
    return X


def fit_ols(df: pd.DataFrame) -> sm.regression.linear_model.RegressionResultsWrapper:
    y = df["Yield"].astype(float)
    X = build_design_matrix(df)
    X_const = sm.add_constant(X, has_constant="add")
    model = sm.OLS(y, X_const, missing="raise")
    return model.fit()


def persist_weights(
    result: sm.regression.linear_model.RegressionResultsWrapper,
    df: pd.DataFrame,
) -> dict:
    params = result.params.to_dict()
    intercept = float(params.pop("const", 0.0))
    coef = {name: float(params.get(name, 0.0)) for name in REGRESSORS}
    for m in range(2, 13):
        coef[f"month_{m}"] = float(params.get(f"month_{m}", 0.0))

    fitted = result.fittedvalues
    residuals = df["Yield"].astype(float) - fitted
    rmse = float(np.sqrt(np.mean(residuals ** 2)))

    weights = {
        "intercept": intercept,
        "coef": coef,
        "baseline_month": BASELINE_MONTH,
        "trained_window": f"{df['Date'].min()}..{df['Date'].max()}",
        "n_obs": int(len(df)),
        "climatology": {
            "source": "NASA POWER monthly (climate Excel 01_MY_PRCP_History / 02_MY_TAVG_History)",
            "method": "same-calendar-month mean",
        },
        "trend": {
            "feature": TREND_FEATURE,
            "baseline_ym": "2015-01",
            "unit": "months since baseline",
            "purpose": "absorb structural year-over-year yield growth so climate signal is not polluted",
        },
        "rolling_window": {
            "PRCP_DEV_3m": "3-month rolling mean of PRCP_DEV (mm/month)",
            "TAVG_DEV_3m": "3-month rolling mean of TAVG_DEV (degC)",
            "rationale": "palm yield responds to cumulative climate stress, not single-month spikes",
        },
        "selected_lags": {"ONI": 12, "PRCP_DEV_3m_window": 3, "TAVG_DEV_3m_window": 3},
        "metrics": {
            "r2": float(result.rsquared),
            "r2_adj": float(result.rsquared_adj),
            "rmse": rmse,
            "aic": float(result.aic),
            "bic": float(result.bic),
        },
        "p_values": {k: float(v) for k, v in result.pvalues.items()},
    }

    WEIGHTS_JSON.write_text(json.dumps(weights, indent=2, ensure_ascii=False), encoding="utf-8")
    return weights


def plot_actual_vs_pred(df: pd.DataFrame, fitted: pd.Series) -> None:
    """绘制真实 Yield vs 模型拟合 Yield 的时间序列对比。"""
    fig, ax = plt.subplots(figsize=(11, 4.2))
    ax.plot(df["Date"], df["Yield"], color="#1F4E78", linewidth=1.6, label="Actual Yield")
    ax.plot(
        df["Date"],
        fitted,
        color="#E07B00",
        linewidth=1.6,
        linestyle="--",
        label="Fitted Yield",
    )
    ax.set_title("Palm oil monthly yield: actual vs OLS fit (2015-2025, Trend + 3m rolling climate)")
    ax.set_ylabel("Yield (tonnes / hectare)")
    ax.set_xlabel("Month")
    tick_positions = list(range(0, len(df), 12))
    ax.set_xticks(tick_positions)
    ax.set_xticklabels([df["Date"].iloc[i] for i in tick_positions], rotation=45)
    ax.grid(True, axis="y", linestyle=":", alpha=0.5)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIT_PNG, dpi=150)
    plt.close(fig)


def plot_trend_decomposition(
    df: pd.DataFrame,
    result: sm.regression.linear_model.RegressionResultsWrapper,
) -> None:
    """把单产拆成: 结构性趋势 + (季节项 + 气候项) 两部分, 帮助直观看 A1 的作用。"""
    beta_trend = float(result.params.get(TREND_FEATURE, 0.0))
    intercept = float(result.params.get("const", 0.0))
    trend_component = intercept + beta_trend * df[TREND_FEATURE].astype(float)
    detrended = df["Yield"].astype(float) - beta_trend * df[TREND_FEATURE].astype(float)
    seasonal_climate_fit = result.fittedvalues - beta_trend * df[TREND_FEATURE].astype(float)

    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)

    axes[0].plot(df["Date"], df["Yield"], color="#1F4E78", linewidth=1.5, label="Actual Yield")
    axes[0].plot(
        df["Date"],
        trend_component,
        color="#2A9D8F",
        linewidth=2.0,
        label=f"Structural trend: {intercept:.4f} + {beta_trend:.6f}·t",
    )
    axes[0].set_title("Step 1 (A1): isolate structural trend")
    axes[0].set_ylabel("Yield (tonnes / hectare)")
    axes[0].grid(True, axis="y", linestyle=":", alpha=0.5)
    axes[0].legend()

    axes[1].plot(df["Date"], detrended, color="#1F4E78", linewidth=1.5, label="Detrended Yield")
    axes[1].plot(
        df["Date"],
        seasonal_climate_fit,
        color="#E07B00",
        linewidth=1.5,
        linestyle="--",
        label="Seasonal + climate fit (after removing trend)",
    )
    axes[1].set_title("Step 2 (A2): seasonal + 3m rolling climate explain the rest")
    axes[1].set_ylabel("Yield (tonnes / hectare)")
    axes[1].grid(True, axis="y", linestyle=":", alpha=0.5)
    axes[1].legend()

    tick_positions = list(range(0, len(df), 12))
    axes[1].set_xticks(tick_positions)
    axes[1].set_xticklabels([df["Date"].iloc[i] for i in tick_positions], rotation=45)

    fig.tight_layout()
    fig.savefig(TREND_PNG, dpi=150)
    plt.close(fig)


def plot_partial_effects(
    result: sm.regression.linear_model.RegressionResultsWrapper,
    df: pd.DataFrame,
) -> None:
    """为三个气候变量分别画偏回归图, 标注 Beta / R^2 / p 值。"""
    exog_names = list(result.model.exog_names)
    design = build_design_matrix(df)
    frame = pd.concat([df[["Yield"]].reset_index(drop=True), design.reset_index(drop=True)], axis=1)

    for var, path in EFFECT_PNGS.items():
        fig, ax = plt.subplots(figsize=(5.5, 4.4))
        plot_partregress(
            endog="Yield",
            exog_i=var,
            exog_others=[name for name in exog_names if name not in {"const", var}],
            data=frame,
            obs_labels=False,
            ax=ax,
        )
        beta = float(result.params[var])
        pval = float(result.pvalues[var])
        r2 = float(result.rsquared)
        ax.set_title(f"Partial effect: {var}\nbeta={beta:.4g}  p={pval:.3g}  model R^2={r2:.3f}")
        ax.grid(True, linestyle=":", alpha=0.5)
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        plt.close(fig)


def main() -> None:
    df = load_dataset()
    result = fit_ols(df)
    print(result.summary())

    weights = persist_weights(result, df)
    plot_actual_vs_pred(df, result.fittedvalues)
    plot_trend_decomposition(df, result)
    plot_partial_effects(result, df)

    metrics = weights["metrics"]
    print(
        f"\n[ok] weights -> {WEIGHTS_JSON}\n"
        f"[metrics] R2={metrics['r2']:.4f}  R2_adj={metrics['r2_adj']:.4f}  "
        f"RMSE={metrics['rmse']:.5f}  AIC={metrics['aic']:.2f}  BIC={metrics['bic']:.2f}\n"
        f"[plots] {FIT_PNG.name}, {TREND_PNG.name}, "
        + ", ".join(p.name for p in EFFECT_PNGS.values())
    )


if __name__ == "__main__":
    main()
