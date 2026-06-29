# -*- coding: utf-8 -*-
"""温度对棕榈油单产影响的三维度深化研究。

维度 a 优化积温窗口长度: 搜索 1-12 月温度滚动距平窗口, 看哪个窗口的温度信号
        最显著、样本外预测最好。
维度 b 高温/低温非对称: 把温度距平拆成偏热(>0)/偏冷(<0)两部分, 检验单产到底
        是怕热还是怕冷 (对称 vs 仅热 vs 仅冷 vs 双侧)。
维度 c 温度×降水空间交互: 在西马/砂拉越/沙巴三区分别构建 温度×降水 交互项与
        "又热又旱"复合胁迫项, 检验空间交互是否比全国单一交互更有解释/预测力。

统一评估口径:
  固定结构 const + Trend + 月份哑变量 (吸收趋势/季节);
  基础气候项 ONI_lag12 + PRCP_DEV_3m, 仅替换/新增温度相关项;
  训练 2010-01~2023-12, 样本外验证 2024-01~2026-05;
  报告 训练期系数/显著性 与 样本外 RMSE/方向命中。

输出:
  code/model/temp_research/dim_a_window.csv / .png
  code/model/temp_research/dim_b_asymmetry.csv / .png
  code/model/temp_research/dim_c_spatial.csv / .png
  code/model/temp_research/summary.md
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from feature_builder import build_features
import modeling_utils as mu

OUT_DIR = Path(__file__).resolve().parent / "temp_research"
TRAIN_START, TRAIN_END = "2010-01", "2023-12"
TEST_START, TEST_END = "2024-01", "2026-05"
BASE = ["ONI_lag12", "PRCP_DEV_3m"]
PRCP_WINDOW = 3


def evaluate(df: pd.DataFrame, climate_features: List[str]) -> Dict[str, float]:
    """在训练期拟合, 返回训练显著性 + 样本外指标。最后一个气候项视为'关注项'。"""
    train_mask = mu.date_mask(df, TRAIN_START, TRAIN_END)
    test_mask = mu.date_mask(df, TEST_START, TEST_END)
    fit = mu.fit_ols(df, climate_features, train_mask, test_mask)
    res = fit.result
    pred = mu.predict(fit, df, fit.test_idx)
    m = mu.metrics(df.loc[fit.test_idx, "Yield"], pred)
    focus = climate_features[-1]
    out = {
        "n_train": int(res.nobs),
        "adj_r2": float(res.rsquared_adj),
        "aic": float(res.aic),
        "focus_beta": float(res.params.get(focus, np.nan)),
        "focus_p": float(res.pvalues.get(focus, np.nan)),
        "test_rmse": m["rmse"],
        "test_mae": m["mae"],
        "test_dir_hit": m["dir_hit"],
    }
    return out


# ----------------------------- 维度 a -----------------------------
def dim_a_window(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for w in range(1, 13):
        feats = [*BASE, f"TAVG_DEV_{w}m"]
        r = evaluate(df, feats)
        r["window_months"] = w
        rows.append(r)
    tab = pd.DataFrame(rows).set_index("window_months")
    tab.to_csv(OUT_DIR / "dim_a_window.csv")

    fig, ax1 = plt.subplots(figsize=(8, 4.6))
    ax1.plot(tab.index, tab["test_rmse"], "o-", color="#C03A2B", label="Out-of-sample RMSE (2024-2026)")
    ax1.set_xlabel("Temperature accumulation window (months)")
    ax1.set_ylabel("OOS RMSE", color="#C03A2B")
    ax1.tick_params(axis="y", labelcolor="#C03A2B")
    ax2 = ax1.twinx()
    ax2.plot(tab.index, -np.log10(tab["focus_p"].clip(lower=1e-12)), "s--", color="#1F4E78",
             label="Train significance  -log10(p)")
    ax2.axhline(-np.log10(0.05), color="gray", ls=":", lw=1)
    ax2.set_ylabel("Train -log10(p) of temperature", color="#1F4E78")
    ax2.tick_params(axis="y", labelcolor="#1F4E78")
    ax1.set_xticks(range(1, 13))
    ax1.set_title("Dim a: temperature accumulation window vs signal strength")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "dim_a_window.png", dpi=150)
    plt.close(fig)
    return tab


# ----------------------------- 维度 b -----------------------------
def dim_b_asymmetry(df: pd.DataFrame, w: int) -> pd.DataFrame:
    specs = {
        "Symmetric (TAVG_DEV)": [*BASE, f"TAVG_DEV_{w}m"],
        "Heat only (>=0)": [*BASE, f"TAVG_HEAT_{w}m"],
        "Cold only (<=0)": [*BASE, f"TAVG_COLD_{w}m"],
        "Asymmetric (heat+cold)": [*BASE, f"TAVG_HEAT_{w}m", f"TAVG_COLD_{w}m"],
    }
    rows = []
    train_mask = mu.date_mask(df, TRAIN_START, TRAIN_END)
    test_mask = mu.date_mask(df, TEST_START, TEST_END)
    for name, feats in specs.items():
        fit = mu.fit_ols(df, feats, train_mask, test_mask)
        res = fit.result
        pred = mu.predict(fit, df, fit.test_idx)
        m = mu.metrics(df.loc[fit.test_idx, "Yield"], pred)
        row = {"model": name, "adj_r2": float(res.rsquared_adj),
               "test_rmse": m["rmse"], "test_dir_hit": m["dir_hit"]}
        for term in [f"TAVG_DEV_{w}m", f"TAVG_HEAT_{w}m", f"TAVG_COLD_{w}m"]:
            if term in res.params.index:
                row[f"beta[{term}]"] = float(res.params[term])
                row[f"p[{term}]"] = float(res.pvalues[term])
        rows.append(row)
    tab = pd.DataFrame(rows).set_index("model")
    tab.to_csv(OUT_DIR / "dim_b_asymmetry.csv")

    heat_b = tab.loc["Asymmetric (heat+cold)", f"beta[TAVG_HEAT_{w}m]"]
    cold_b = tab.loc["Asymmetric (heat+cold)", f"beta[TAVG_COLD_{w}m]"]
    fig, ax = plt.subplots(figsize=(6.2, 4.4))
    bars = ax.bar(["Heat part\n(TAVG_DEV>0)", "Cold part\n(TAVG_DEV<0)"], [heat_b, cold_b],
                  color=["#C03A2B", "#1F6FB2"])
    ax.axhline(0, color="black", lw=0.8)
    ax.set_ylabel(f"Yield sensitivity (beta), window={w}m")
    ax.set_title("Dim b: asymmetric temperature effect on yield")
    for b, v in zip(bars, [heat_b, cold_b]):
        ax.text(b.get_x() + b.get_width() / 2, v, f"{v:.4f}", ha="center",
                va="bottom" if v >= 0 else "top")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "dim_b_asymmetry.png", dpi=150)
    plt.close(fig)
    return tab


# ----------------------------- 维度 c -----------------------------
def dim_c_spatial(df: pd.DataFrame, w: int) -> pd.DataFrame:
    base3 = [*BASE, f"TAVG_DEV_{w}m"]
    specs = {
        "Base 3-factor (no interaction)": base3,
        "+National T×P interaction": [*base3, f"INTX_NAT_{w}m"],
        "+National hot-dry compound": [*base3, f"HOTDRY_NAT_{w}m"],
        "+3-region hot-dry (sum)": [*base3, f"HOTDRY_ALL_{w}m"],
        "+West interaction": [*base3, f"INTX_West_{w}m"],
        "+Sarawak interaction": [*base3, f"INTX_Sarawak_{w}m"],
        "+Sabah interaction": [*base3, f"INTX_Sabah_{w}m"],
        "+West hot-dry": [*base3, f"HOTDRY_West_{w}m"],
        "+Sarawak hot-dry": [*base3, f"HOTDRY_Sarawak_{w}m"],
        "+Sabah hot-dry": [*base3, f"HOTDRY_Sabah_{w}m"],
    }
    rows = []
    train_mask = mu.date_mask(df, TRAIN_START, TRAIN_END)
    test_mask = mu.date_mask(df, TEST_START, TEST_END)
    for name, feats in specs.items():
        fit = mu.fit_ols(df, feats, train_mask, test_mask)
        res = fit.result
        pred = mu.predict(fit, df, fit.test_idx)
        m = mu.metrics(df.loc[fit.test_idx, "Yield"], pred)
        focus = feats[-1]
        rows.append({
            "model": name, "added_term": focus if focus != f"TAVG_DEV_{w}m" else "-",
            "adj_r2": float(res.rsquared_adj), "aic": float(res.aic),
            "added_beta": float(res.params.get(focus, np.nan)) if focus != f"TAVG_DEV_{w}m" else np.nan,
            "added_p": float(res.pvalues.get(focus, np.nan)) if focus != f"TAVG_DEV_{w}m" else np.nan,
            "test_rmse": m["rmse"], "test_dir_hit": m["dir_hit"],
        })
    tab = pd.DataFrame(rows).set_index("model")
    tab.to_csv(OUT_DIR / "dim_c_spatial.csv")

    fig, ax = plt.subplots(figsize=(9, 4.8))
    colors = ["#888"] + ["#2A9D8F"] * 3 + ["#E07B00"] * 3 + ["#C03A2B"] * 3
    ax.barh(range(len(tab)), tab["test_rmse"].values, color=colors[:len(tab)])
    ax.set_yticks(range(len(tab)))
    ax.set_yticklabels(tab.index, fontsize=8)
    ax.invert_yaxis()
    ax.axvline(tab["test_rmse"].iloc[0], color="gray", ls=":", lw=1, label="base RMSE")
    ax.set_xlabel("Out-of-sample RMSE (2024-2026), lower is better")
    ax.set_title(f"Dim c: spatial temperature×precip interaction (window={w}m)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUT_DIR / "dim_c_spatial.png", dpi=150)
    plt.close(fig)
    return tab


def _df_to_md(df: pd.DataFrame) -> str:
    """把 DataFrame 转成 markdown 表格 (避免依赖 tabulate)。"""
    d = df.reset_index()
    head = "| " + " | ".join(str(c) for c in d.columns) + " |"
    sep = "| " + " | ".join("---" for _ in d.columns) + " |"
    body = ["| " + " | ".join(str(v) for v in row) + " |"
            for row in d.itertuples(index=False)]
    return "\n".join([head, sep, *body])


def pick_best_window(tab_a: pd.DataFrame) -> int:
    """选窗口: 训练显著 (p<0.1) 中 OOS RMSE 最低; 若无显著者则取 OOS RMSE 最低。"""
    sig = tab_a[tab_a["focus_p"] < 0.10]
    pool = sig if not sig.empty else tab_a
    return int(pool["test_rmse"].idxmin())


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = build_features()
    df = mu.add_month_dummies(df)

    tab_a = dim_a_window(df)
    best_w = pick_best_window(tab_a)
    tab_b = dim_b_asymmetry(df, best_w)
    tab_c = dim_c_spatial(df, best_w)

    lines = ["# 温度对单产影响 — 三维度研究小结\n",
             f"训练 {TRAIN_START}~{TRAIN_END} (含2010-2014面积回推), 验证 {TEST_START}~{TEST_END}\n",
             f"固定结构 const+Trend+月份哑变量; 基础项 ONI_lag12 + PRCP_DEV_{PRCP_WINDOW}m\n",
             "\n## 维度a 积温窗口\n",
             _df_to_md(tab_a.round(5)),
             f"\n\n=> 最优温度积温窗口: **{best_w} 个月**\n",
             "\n## 维度b 高温/低温非对称\n",
             _df_to_md(tab_b.round(5)),
             "\n\n## 维度c 温度×降水空间交互\n",
             _df_to_md(tab_c.round(5)), "\n"]
    (OUT_DIR / "summary.md").write_text("\n".join(lines), encoding="utf-8")

    print("=== 维度a 积温窗口 (节选) ===")
    print(tab_a[["adj_r2", "focus_beta", "focus_p", "test_rmse", "test_dir_hit"]].round(4).to_string())
    print(f"\n>>> 最优积温窗口 = {best_w} 个月\n")
    print("=== 维度b 非对称 ===")
    print(tab_b.round(5).to_string())
    print("\n=== 维度c 空间交互 ===")
    print(tab_c[["added_term", "adj_r2", "added_beta", "added_p", "test_rmse", "test_dir_hit"]].round(5).to_string())


if __name__ == "__main__":
    main()
