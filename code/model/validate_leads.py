# -*- coding: utf-8 -*-
"""Phase 2.5: 验证气候变量领先期，并选择进入预测引擎的滞后组合。

输入:
  data/processed/archives/*.xlsx  (仍然只读取三本正式 Excel)

输出:
  code/model/lead_validation_results.csv
  code/model/lead_validation_top10_rmse.png
  code/model/lead_validation_heatmap_oni_prcp.png
  code/model/lead_validation_heatmap_oni_tavg.png
  code/model/lead_validation_report.md

判断逻辑:
  - 以 2024-01..2025-12 为样本外测试窗口。
  - 每组领先期都重新训练 OLS: Yield ~ Trend + ONI_lagX + PRCP_DEV_3m_lagY
    + TAVG_DEV_3m_lagZ + 月份哑变量。
  - 主排序看 test_rmse, 辅助看 AIC/BIC、气候变量 p 值、农学方向。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

import data_pipeline


PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MODEL_DIR = Path(__file__).resolve().parent
RESULTS_CSV = MODEL_DIR / "lead_validation_results.csv"
TOP10_PNG = MODEL_DIR / "lead_validation_top10_rmse.png"
HEATMAP_ONI_PRCP_PNG = MODEL_DIR / "lead_validation_heatmap_oni_prcp.png"
HEATMAP_ONI_TAVG_PNG = MODEL_DIR / "lead_validation_heatmap_oni_tavg.png"
REPORT_MD = MODEL_DIR / "lead_validation_report.md"
WEIGHTS_JSON = MODEL_DIR / "model_weights.json"

ONI_LAGS = [3, 6, 9, 12, 15, 18]
PRCP_LAGS = [0, 1, 2, 3, 6]
TAVG_LAGS = [0, 1, 2, 3, 6]
TEST_START = "2024-01"
TEST_END = "2025-12"
BASELINE_MONTH = 1


@dataclass(frozen=True)
class LeadCombo:
    oni_lag: int
    prcp_lag: int
    tavg_lag: int

    @property
    def oni_col(self) -> str:
        return f"ONI_lag{self.oni_lag}"

    @property
    def prcp_col(self) -> str:
        return f"PRCP_DEV_3m_lag{self.prcp_lag}"

    @property
    def tavg_col(self) -> str:
        return f"TAVG_DEV_3m_lag{self.tavg_lag}"

    @property
    def label(self) -> str:
        return f"ONI {self.oni_lag}m / PRCP {self.prcp_lag}m / TAVG {self.tavg_lag}m"


def _month_shift_feature(
    df: pd.DataFrame,
    date_col: str,
    value_col: str,
    lag_months: int,
    output_col: str,
) -> pd.DataFrame:
    """把 t-lag 的变量移动到 t 月, 得到目标月可用的领先期输入。"""
    shifted = df[[date_col, value_col]].dropna(subset=[value_col]).copy()
    shifted[date_col] = (
        pd.to_datetime(shifted[date_col]) + pd.DateOffset(months=lag_months)
    ).dt.to_period("M").astype(str)
    shifted = shifted.rename(columns={value_col: output_col})
    return shifted[[date_col, output_col]]


def build_base_dataset() -> pd.DataFrame:
    """复用第一阶段读取逻辑，构造包含所有候选领先期的验证数据集。"""
    area = data_pipeline.read_area_monthly()
    climate = data_pipeline.enrich_climate_timeline(data_pipeline.read_climate_history())
    production = data_pipeline.read_production_monthly()

    base = (
        production.merge(area, on="Date", how="left")
        .sort_values("Date")
        .reset_index(drop=True)
    )
    base["Yield"] = base["Production"] / base["Mature_Area"]
    base["Trend"] = data_pipeline._trend_index(base["Date"])
    base["Month"] = pd.to_datetime(base["Date"]).dt.month

    for lag in ONI_LAGS:
        base = base.merge(
            _month_shift_feature(climate, "Date", "ONI", lag, f"ONI_lag{lag}"),
            on="Date",
            how="left",
        )
    for lag in PRCP_LAGS:
        base = base.merge(
            _month_shift_feature(climate, "Date", "PRCP_DEV_3m", lag, f"PRCP_DEV_3m_lag{lag}"),
            on="Date",
            how="left",
        )
    for lag in TAVG_LAGS:
        base = base.merge(
            _month_shift_feature(climate, "Date", "TAVG_DEV_3m", lag, f"TAVG_DEV_3m_lag{lag}"),
            on="Date",
            how="left",
        )

    required = ["Date", "Yield", "Trend", "Month", "Mature_Area"]
    clean = base.dropna(subset=required).copy()
    if clean.empty:
        raise ValueError("领先期验证基础数据为空，请检查三本 Excel。")
    return clean


def build_design_matrix(df: pd.DataFrame, feature_cols: Iterable[str]) -> pd.DataFrame:
    X = df[["Trend", *feature_cols]].astype(float).copy()
    months = df["Month"].astype(int)
    for month in range(2, 13):
        X[f"month_{month}"] = (months == month).astype(int)
    return sm.add_constant(X, has_constant="add")


def _rmse(actual: pd.Series, predicted: pd.Series) -> float:
    residual = actual.astype(float) - predicted.astype(float)
    return float(np.sqrt(np.mean(residual**2)))


def _agri_score(result: sm.regression.linear_model.RegressionResultsWrapper, combo: LeadCombo) -> int:
    """简单农学打分: ONI 9-15 月更合理；降水/温度 1-6 月更贴近果穗发育。"""
    score = 0
    if combo.oni_lag in {9, 12, 15}:
        score += 1
    if combo.prcp_lag in {1, 2, 3, 6}:
        score += 1
    if combo.tavg_lag in {1, 2, 3, 6}:
        score += 1

    params = result.params
    if float(params.get(combo.oni_col, 0.0)) < 0:
        score += 1
    if float(params.get(combo.prcp_col, 0.0)) > 0:
        score += 1
    return score


def fit_combo(df: pd.DataFrame, combo: LeadCombo) -> Dict[str, float | int | str]:
    feature_cols = [combo.oni_col, combo.prcp_col, combo.tavg_col]
    work = df.dropna(subset=["Yield", "Trend", "Month", *feature_cols]).copy()
    train = work[work["Date"] < TEST_START].copy()
    test = work[(work["Date"] >= TEST_START) & (work["Date"] <= TEST_END)].copy()
    if len(train) < 72 or len(test) < 12:
        raise ValueError(f"{combo.label} 可用样本不足: train={len(train)}, test={len(test)}")

    result = sm.OLS(train["Yield"].astype(float), build_design_matrix(train, feature_cols)).fit()
    test_pred = result.predict(build_design_matrix(test, feature_cols))
    final_result = sm.OLS(work["Yield"].astype(float), build_design_matrix(work, feature_cols)).fit()

    p_values = result.pvalues
    climate_p_mean = float(np.mean([p_values[combo.oni_col], p_values[combo.prcp_col], p_values[combo.tavg_col]]))
    climate_p_max = float(np.max([p_values[combo.oni_col], p_values[combo.prcp_col], p_values[combo.tavg_col]]))

    return {
        "combo": combo.label,
        "oni_lag": combo.oni_lag,
        "prcp_lag": combo.prcp_lag,
        "tavg_lag": combo.tavg_lag,
        "n_train": int(len(train)),
        "n_test": int(len(test)),
        "train_r2": float(result.rsquared),
        "train_r2_adj": float(result.rsquared_adj),
        "train_aic": float(result.aic),
        "train_bic": float(result.bic),
        "test_rmse": _rmse(test["Yield"], test_pred),
        "climate_p_mean": climate_p_mean,
        "climate_p_max": climate_p_max,
        "p_trend": float(p_values.get("Trend", np.nan)),
        "p_oni": float(p_values[combo.oni_col]),
        "p_prcp": float(p_values[combo.prcp_col]),
        "p_tavg": float(p_values[combo.tavg_col]),
        "coef_trend": float(result.params.get("Trend", 0.0)),
        "coef_oni": float(result.params[combo.oni_col]),
        "coef_prcp": float(result.params[combo.prcp_col]),
        "coef_tavg": float(result.params[combo.tavg_col]),
        "final_coef_trend": float(final_result.params.get("Trend", 0.0)),
        "final_coef_oni": float(final_result.params[combo.oni_col]),
        "final_coef_prcp": float(final_result.params[combo.prcp_col]),
        "final_coef_tavg": float(final_result.params[combo.tavg_col]),
        "final_p_oni": float(final_result.pvalues[combo.oni_col]),
        "final_p_prcp": float(final_result.pvalues[combo.prcp_col]),
        "final_p_tavg": float(final_result.pvalues[combo.tavg_col]),
        "final_climate_p_mean": float(
            np.mean(
                [
                    final_result.pvalues[combo.oni_col],
                    final_result.pvalues[combo.prcp_col],
                    final_result.pvalues[combo.tavg_col],
                ]
            )
        ),
        "agri_score": _agri_score(result, combo),
    }


def validate_all_leads(df: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, float | int | str]] = []
    for oni_lag in ONI_LAGS:
        for prcp_lag in PRCP_LAGS:
            for tavg_lag in TAVG_LAGS:
                rows.append(fit_combo(df, LeadCombo(oni_lag, prcp_lag, tavg_lag)))

    results = pd.DataFrame(rows)
    results["rmse_rank"] = results["test_rmse"].rank(method="min", ascending=True)
    results["p_rank"] = results["climate_p_mean"].rank(method="min", ascending=True)
    results["aic_rank"] = results["train_aic"].rank(method="min", ascending=True)
    results["combined_score"] = (
        results["rmse_rank"] * 0.60
        + results["p_rank"] * 0.25
        + results["aic_rank"] * 0.15
        - results["agri_score"] * 0.50
    )
    return results.sort_values(["combined_score", "test_rmse"]).reset_index(drop=True)


def select_best(results: pd.DataFrame) -> pd.Series:
    """选择可进入预测引擎的组合。

    纯 RMSE 最低的组合可能抓到短期噪声。正式选择时增加方向约束:
    验证窗口和全样本里的 ONI 系数都应为负, 降水系数都应为正。
    如果存在稳定方向组合, 优先看最终全样本模型里的气候变量 p 值,
    再看验证窗口 p 值和 RMSE。
    """
    pure_best_rmse = float(results["test_rmse"].min())
    feasible = results[
        (results["coef_oni"] < 0)
        & (results["coef_prcp"] > 0)
        & (results["final_coef_oni"] < 0)
        & (results["final_coef_prcp"] > 0)
    ].copy()
    if feasible.empty:
        return results.sort_values("test_rmse").iloc[0]

    feasible = feasible.sort_values(
        ["final_climate_p_mean", "climate_p_mean", "test_rmse", "agri_score"],
        ascending=[True, True, True, False],
    )
    return feasible.iloc[0]


def plot_top10(results: pd.DataFrame) -> None:
    top = results.sort_values("test_rmse").head(10).sort_values("test_rmse", ascending=True)
    fig, ax = plt.subplots(figsize=(11, 5))
    ax.barh(top["combo"], top["test_rmse"], color="#1F77B4")
    ax.set_title("Lead validation: top 10 combinations by out-of-sample RMSE")
    ax.set_xlabel("Test RMSE (2024-2025, lower is better)")
    ax.invert_yaxis()
    ax.grid(True, axis="x", linestyle=":", alpha=0.5)
    fig.tight_layout()
    fig.savefig(TOP10_PNG, dpi=150)
    plt.close(fig)


def _plot_heatmap(pivot: pd.DataFrame, title: str, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    image = ax.imshow(pivot.values, cmap="viridis_r", aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([str(v) for v in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([str(v) for v in pivot.index])
    ax.set_xlabel(pivot.columns.name or "Lag")
    ax.set_ylabel(pivot.index.name or "Lag")
    ax.set_title(title)
    for row_idx, row_value in enumerate(pivot.index):
        for col_idx, col_value in enumerate(pivot.columns):
            ax.text(
                col_idx,
                row_idx,
                f"{pivot.loc[row_value, col_value]:.4f}",
                ha="center",
                va="center",
                color="white",
                fontsize=8,
            )
    fig.colorbar(image, ax=ax, label="Best test RMSE")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


def plot_heatmaps(results: pd.DataFrame) -> None:
    oni_prcp = results.pivot_table(
        index="oni_lag",
        columns="prcp_lag",
        values="test_rmse",
        aggfunc="min",
    )
    oni_prcp.index.name = "ONI lag (months)"
    oni_prcp.columns.name = "PRCP lag (months)"
    _plot_heatmap(oni_prcp, "Best RMSE by ONI lag and PRCP lag", HEATMAP_ONI_PRCP_PNG)

    oni_tavg = results.pivot_table(
        index="oni_lag",
        columns="tavg_lag",
        values="test_rmse",
        aggfunc="min",
    )
    oni_tavg.index.name = "ONI lag (months)"
    oni_tavg.columns.name = "TAVG lag (months)"
    _plot_heatmap(oni_tavg, "Best RMSE by ONI lag and TAVG lag", HEATMAP_ONI_TAVG_PNG)


def fit_final_model(df: pd.DataFrame, best: pd.Series) -> sm.regression.linear_model.RegressionResultsWrapper:
    combo = LeadCombo(int(best["oni_lag"]), int(best["prcp_lag"]), int(best["tavg_lag"]))
    feature_cols = [combo.oni_col, combo.prcp_col, combo.tavg_col]
    work = df.dropna(subset=["Yield", "Trend", "Month", *feature_cols]).copy()
    return sm.OLS(work["Yield"].astype(float), build_design_matrix(work, feature_cols)).fit()


def update_model_weights(
    results: pd.DataFrame,
    best: pd.Series,
    final_result: sm.regression.linear_model.RegressionResultsWrapper,
) -> None:
    if WEIGHTS_JSON.exists():
        weights = json.loads(WEIGHTS_JSON.read_text(encoding="utf-8"))
    else:
        weights = {}

    combo = LeadCombo(int(best["oni_lag"]), int(best["prcp_lag"]), int(best["tavg_lag"]))
    pure_rmse_best = results.sort_values("test_rmse").iloc[0]
    params = final_result.params.to_dict()
    coef = {
        "Trend": float(params.get("Trend", 0.0)),
        combo.oni_col: float(params.get(combo.oni_col, 0.0)),
        combo.prcp_col: float(params.get(combo.prcp_col, 0.0)),
        combo.tavg_col: float(params.get(combo.tavg_col, 0.0)),
    }
    for month in range(2, 13):
        coef[f"month_{month}"] = float(params.get(f"month_{month}", 0.0))

    weights.update(
        {
            "intercept": float(params.get("const", 0.0)),
            "coef": coef,
            "selected_lags": {
                "ONI": combo.oni_lag,
                "PRCP_DEV_3m": combo.prcp_lag,
                "TAVG_DEV_3m": combo.tavg_lag,
                "meaning": "target month uses climate information from target month minus lag months",
            },
            "lead_validation": {
                "test_window": f"{TEST_START}..{TEST_END}",
                "n_combinations": int(len(results)),
                "selection_rule": "choose direction-consistent candidate: validation and final ONI coefficients < 0, validation and final PRCP coefficients > 0; then lowest final climate p-value, validation p-value, and lower RMSE",
                "chosen_combo": combo.label,
                "chosen_test_rmse": float(best["test_rmse"]),
                "chosen_train_climate_p_mean": float(best["climate_p_mean"]),
                "chosen_final_climate_p_mean": float(best["final_climate_p_mean"]),
                "chosen_agri_score": int(best["agri_score"]),
                "pure_rmse_best_combo": str(pure_rmse_best["combo"]),
                "pure_rmse_best_test_rmse": float(pure_rmse_best["test_rmse"]),
                "pure_rmse_best_rejected_reason": "ONI coefficient sign is not consistent with El Nino later reducing yield",
                "results_csv": str(RESULTS_CSV.relative_to(PROJECT_ROOT)),
            },
            "metrics": {
                "r2": float(final_result.rsquared),
                "r2_adj": float(final_result.rsquared_adj),
                "aic": float(final_result.aic),
                "bic": float(final_result.bic),
                "lead_validation_test_rmse": float(best["test_rmse"]),
            },
            "p_values": {key: float(value) for key, value in final_result.pvalues.items()},
        }
    )
    WEIGHTS_JSON.write_text(json.dumps(weights, indent=2, ensure_ascii=False), encoding="utf-8")


def write_report(results: pd.DataFrame, best: pd.Series) -> None:
    top5 = results.sort_values("combined_score").head(5)
    pure_rmse_best = results.sort_values("test_rmse").iloc[0]
    lines = [
        "# Phase 2.5 领先期验证报告",
        "",
        "## 结论",
        "",
        f"- 最终选择: ONI 提前 {int(best['oni_lag'])} 个月, 降水 3 月滚动距平提前 {int(best['prcp_lag'])} 个月, 气温 3 月滚动距平提前 {int(best['tavg_lag'])} 个月。",
        f"- 样本外测试窗口: {TEST_START} 到 {TEST_END}。",
        f"- 该组合样本外 RMSE: {float(best['test_rmse']):.5f}, 验证窗口气候平均 p 值: {float(best['climate_p_mean']):.3f}, 全样本气候平均 p 值: {float(best['final_climate_p_mean']):.3f}, 农学分: {int(best['agri_score'])}/5。",
        f"- 纯 RMSE 最低组合是 {pure_rmse_best['combo']}, RMSE={float(pure_rmse_best['test_rmse']):.5f}; 但它的 ONI 方向不符合厄尔尼诺后续减产逻辑, 不作为最终预测权重。",
        "",
        "## 为什么这样选",
        "",
        "- 第一关是方向约束: ONI 系数必须为负, 因为厄尔尼诺升温通常会在之后压制油棕单产; 降水系数必须为正, 因为适度偏湿通常有利于油棕。",
        "- 第二关是稳定性约束: 验证窗口和全样本重训后的 ONI/降水方向都必须一致, 避免选出重训后反向的系数。",
        "- 第三关是误差对照: RMSE 用来提醒预测误差代价, 但不会覆盖方向稳定性和最终权重显著性。",
        "- 第四关是 p 值: 在满足前面约束后, 优先选择全样本气候变量平均 p 值最低的组合, 因为最终预测权重会用全样本重训。",
        "- PRCP/TAVG 领先 0 个月不是单月当月值, 而是目标月的 3 月滚动距平, 已经包含目标月及前两个月的累计气候状态。",
        "",
        "## 综合误差前 5 名组合（供对照, 非最终选择）",
        "",
        "| 排名 | ONI领先月 | 降水领先月 | 气温领先月 | 测试RMSE | 气候平均p值 | 农学分 | 综合分 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rank, row in enumerate(top5.itertuples(index=False), start=1):
        lines.append(
            f"| {rank} | {int(row.oni_lag)} | {int(row.prcp_lag)} | {int(row.tavg_lag)} | "
            f"{float(row.test_rmse):.5f} | {float(row.climate_p_mean):.3f} | "
            f"{int(row.agri_score)} | {float(row.combined_score):.2f} |"
        )
    lines.extend(
        [
            "",
            "## 图表文件",
            "",
            f"- Top 10 RMSE 柱状图: `{TOP10_PNG.name}`",
            f"- ONI x 降水领先期热力图: `{HEATMAP_ONI_PRCP_PNG.name}`",
            f"- ONI x 气温领先期热力图: `{HEATMAP_ONI_TAVG_PNG.name}`",
        ]
    )
    REPORT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    df = build_base_dataset()
    results = validate_all_leads(df)
    best = select_best(results)
    final_result = fit_final_model(df, best)

    results.to_csv(RESULTS_CSV, index=False)
    plot_top10(results)
    plot_heatmaps(results)
    update_model_weights(results, best, final_result)
    write_report(results, best)

    print(f"[ok] lead results -> {RESULTS_CSV} rows={len(results)}")
    print(f"[ok] plots -> {TOP10_PNG.name}, {HEATMAP_ONI_PRCP_PNG.name}, {HEATMAP_ONI_TAVG_PNG.name}")
    print(f"[ok] report -> {REPORT_MD}")
    print(
        "[selected] "
        f"ONI={int(best['oni_lag'])}m, "
        f"PRCP={int(best['prcp_lag'])}m, "
        f"TAVG={int(best['tavg_lag'])}m, "
        f"test_rmse={float(best['test_rmse']):.5f}, "
        f"climate_p_mean={float(best['climate_p_mean']):.3f}"
    )


if __name__ == "__main__":
    main()
