# -*- coding: utf-8 -*-
"""三维 (ONI + 降水 + 温度) 棕榈油单产预测模型 + 2024-2026 样本外验证。

模型族 (均含 const + Trend + 月份哑变量 吸收趋势/季节):
  M0_baseline  : ONI_lag12 + PRCP_DEV_3m + TAVG_DEV_3m            (前期结构, 对照)
  M1_3factor   : ONI_lag12 + PRCP_DEV_3m + TAVG_DEV_10m           (温度积温窗口优化)
  M2_spatial   : M1 + INTX_West_10m                               (加西马温×降空间交互)

面积/样本变体:
  full   : 训练 2010-01~2023-12 (含 2010-2014 面积线性回推, 用户要求的口径)
  real   : 训练 2015-01~2023-12 (仅真实 MPOB 面积, 规避回推高估)
  两者样本外验证窗口相同: 2024-01~2026-05。

输出:
  code/model/model3d_validation_metrics.csv   全部模型×变体的训练/样本外指标
  code/model/model3d_weights.json             推荐模型权重 (供部署/复算)
  code/model/figures/model3d_*.png            验证可视化
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from feature_builder import build_features
import modeling_utils as mu

MODEL_DIR = Path(__file__).resolve().parent
FIG_DIR = MODEL_DIR / "figures"
METRICS_CSV = MODEL_DIR / "model3d_validation_metrics.csv"
WEIGHTS_JSON = MODEL_DIR / "model3d_weights.json"

TEST_START, TEST_END = "2024-01", "2026-05"
MODELS: Dict[str, List[str]] = {
    "M0_baseline": ["ONI_lag12", "PRCP_DEV_3m", "TAVG_DEV_3m"],
    "M1_3factor": ["ONI_lag12", "PRCP_DEV_3m", "TAVG_DEV_10m"],
    "M2_spatial": ["ONI_lag12", "PRCP_DEV_3m", "TAVG_DEV_10m", "INTX_West_10m"],
}
TRAIN_VARIANTS = {"full": "2010-01", "real": "2015-01"}
TRAIN_END = "2023-12"


def run_all(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    test_mask = mu.date_mask(df, TEST_START, TEST_END)
    for variant, tstart in TRAIN_VARIANTS.items():
        train_mask = mu.date_mask(df, tstart, TRAIN_END)
        for mname, feats in MODELS.items():
            fit = mu.fit_ols(df, feats, train_mask, test_mask)
            res = fit.result
            pred = mu.predict(fit, df, fit.test_idx)
            m = mu.metrics(df.loc[fit.test_idx, "Yield"], pred)
            row = {"model": mname, "variant": variant, "train_start": tstart,
                   "n_train": int(res.nobs), "adj_r2": float(res.rsquared_adj),
                   "aic": float(res.aic),
                   "test_rmse": m["rmse"], "test_mae": m["mae"],
                   "test_mape%": m["mape"], "test_dir_hit": m["dir_hit"],
                   "test_r2": m["r2_oos"]}
            for f in feats:
                row[f"p[{f}]"] = float(res.pvalues.get(f, np.nan))
            rows.append(row)
    tab = pd.DataFrame(rows)
    tab.to_csv(METRICS_CSV, index=False)
    return tab


def fit_named(df: pd.DataFrame, mname: str, variant: str):
    feats = MODELS[mname]
    train_mask = mu.date_mask(df, TRAIN_VARIANTS[variant], TRAIN_END)
    test_mask = mu.date_mask(df, TEST_START, TEST_END)
    return mu.fit_ols(df, feats, train_mask, test_mask)


def persist_weights(df: pd.DataFrame, mname: str, variant: str, tab: pd.DataFrame) -> None:
    fit = fit_named(df, mname, variant)
    res = fit.result
    sel = tab[(tab.model == mname) & (tab.variant == variant)].iloc[0]
    weights = {
        "model_name": mname,
        "variant": variant,
        "features": MODELS[mname],
        "structure": "const + Trend + month_2..12 + climate features",
        "trained_window": f"{TRAIN_VARIANTS[variant]}..{TRAIN_END}",
        "test_window": f"{TEST_START}..{TEST_END}",
        "intercept": float(res.params.get("const", 0.0)),
        "coef": {k: float(v) for k, v in res.params.items() if k != "const"},
        "p_values": {k: float(v) for k, v in res.pvalues.items()},
        "metrics": {
            "train_adj_r2": float(res.rsquared_adj), "train_aic": float(res.aic),
            "test_rmse": float(sel["test_rmse"]), "test_mae": float(sel["test_mae"]),
            "test_mape_pct": float(sel["test_mape%"]), "test_dir_hit": float(sel["test_dir_hit"]),
            "test_r2": float(sel["test_r2"]),
        },
        "feature_notes": {
            "ONI_lag12": "12 个月前 ONI (El Nino 偏暖 -> 约一年后单产偏低)",
            "PRCP_DEV_3m": "全国降水 3 月滚动距平 (mm/月)",
            "TAVG_DEV_10m": "全国气温 10 月滚动距平 (°C), 温度主效应窗口",
            "INTX_West_10m": "西马 温度距平×降水距平 (10月窗口) 空间交互, 捕捉又热又旱复合胁迫",
        },
    }
    WEIGHTS_JSON.write_text(json.dumps(weights, indent=2, ensure_ascii=False), encoding="utf-8")


def plot_validation(df: pd.DataFrame, mname: str, variant: str) -> None:
    fit = fit_named(df, mname, variant)
    cols = mu.design_columns(MODELS[mname])
    work = df.dropna(subset=["Yield", *cols]).copy()
    in_pred = mu.predict(fit, work, fit.train_idx)
    out_pred = mu.predict(fit, work, fit.test_idx)

    fig, ax = plt.subplots(figsize=(12, 4.6))
    ax.plot(work["Date"], work["Yield"], color="#1F4E78", lw=1.5, label="Actual yield")
    ax.plot(work.loc[fit.train_idx, "Date"], in_pred, color="#2A9D8F", lw=1.3, ls="--",
            label="In-sample fit")
    ax.plot(work.loc[fit.test_idx, "Date"], out_pred, color="#C03A2B", lw=2.0,
            label="Out-of-sample forecast (2024-2026)")
    bnd = work.loc[fit.test_idx, "Date"].min()
    ax.axvline(list(work["Date"]).index(bnd), color="gray", ls=":", lw=1.2)
    ax.text(list(work["Date"]).index(bnd), ax.get_ylim()[1], " train | test", va="top", color="gray")
    ticks = list(range(0, len(work), 12))
    ax.set_xticks(ticks)
    ax.set_xticklabels([work["Date"].iloc[i] for i in ticks], rotation=45)
    ax.set_ylabel("Yield (tonnes/ha)")
    ax.set_title(f"3D model {mname} ({variant}): actual vs fit/forecast")
    ax.grid(True, axis="y", ls=":", alpha=0.5)
    ax.legend(loc="lower left")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "model3d_validation_timeline.png", dpi=150)
    plt.close(fig)

    # 样本外放大 + 散点
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.4))
    td = work.loc[fit.test_idx]
    axes[0].plot(td["Date"], td["Yield"], "o-", color="#1F4E78", label="Actual")
    axes[0].plot(td["Date"], out_pred, "s--", color="#C03A2B", label="Forecast")
    axes[0].set_xticks(range(len(td)))
    axes[0].set_xticklabels(td["Date"], rotation=45, fontsize=8)
    axes[0].set_title("Out-of-sample 2024-2026: monthly")
    axes[0].set_ylabel("Yield (tonnes/ha)")
    axes[0].grid(True, ls=":", alpha=0.5)
    axes[0].legend()
    lo = min(td["Yield"].min(), out_pred.min())
    hi = max(td["Yield"].max(), out_pred.max())
    axes[1].scatter(td["Yield"], out_pred, color="#C03A2B")
    axes[1].plot([lo, hi], [lo, hi], color="gray", ls="--")
    axes[1].set_xlabel("Actual yield")
    axes[1].set_ylabel("Forecast yield")
    axes[1].set_title("Out-of-sample: forecast vs actual")
    axes[1].grid(True, ls=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "model3d_oos_detail.png", dpi=150)
    plt.close(fig)


def main() -> None:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    df = build_features()
    df = mu.add_month_dummies(df)
    tab = run_all(df)

    show = tab[["model", "variant", "n_train", "adj_r2", "test_rmse",
                "test_mae", "test_mape%", "test_dir_hit", "test_r2"]]
    print("=== 三维模型 × 变体 验证指标 ===")
    print(show.round(4).to_string(index=False))

    # 推荐: 样本外 RMSE 最低者
    best = tab.loc[tab["test_rmse"].idxmin()]
    bm, bv = best["model"], best["variant"]
    print(f"\n>>> 推荐模型: {bm} (变体 {bv}) | 样本外 RMSE={best['test_rmse']:.5f} "
          f"MAPE={best['test_mape%']:.2f}% 方向命中={best['test_dir_hit']:.2%}")
    persist_weights(df, bm, bv, tab)
    plot_validation(df, bm, bv)
    print(f"[ok] 权重 -> {WEIGHTS_JSON.name}; 图 -> figures/model3d_*.png")


if __name__ == "__main__":
    main()
