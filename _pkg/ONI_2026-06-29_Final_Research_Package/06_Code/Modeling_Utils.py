# -*- coding: utf-8 -*-
"""三维产量模型与温度研究的共享建模工具。

统一约定:
  - 因变量: Yield (= 月度产量 / 成熟面积)
  - 固定结构: const + Trend + 11 个月份哑变量 (1 月基准) 吸收结构趋势与季节
  - 气候自变量: 调用方传入的特征列 (ONI/降水/温度/交互项)
  - 训练/测试: 按 Date 字符串切分 (含端点)
  - 评估指标: 样本内 R²/调整R²/AIC, 样本外 RMSE/MAE/方向命中率
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence

import numpy as np
import pandas as pd
import statsmodels.api as sm

MONTH_DUMMIES = [f"month_{m}" for m in range(2, 13)]


def add_month_dummies(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    months = out["Month"].astype(int)
    for m in range(2, 13):
        out[f"month_{m}"] = (months == m).astype(int)
    return out


def rolling_dev(series: pd.Series, window: int) -> pd.Series:
    """对已按 Date 升序排列的距平序列做 window 月滚动均值 (积温窗口)。"""
    if window <= 1:
        return series.astype(float)
    return series.rolling(window=window, min_periods=window).mean()


@dataclass
class FitResult:
    result: sm.regression.linear_model.RegressionResultsWrapper
    features: List[str]
    train_idx: pd.Index
    test_idx: pd.Index


def design_columns(climate_features: Sequence[str]) -> List[str]:
    return ["Trend", *climate_features, *MONTH_DUMMIES]


def fit_ols(
    df: pd.DataFrame,
    climate_features: Sequence[str],
    train_mask: pd.Series,
    test_mask: pd.Series | None = None,
) -> FitResult:
    """在 train_mask 上拟合 OLS。df 需已含 month 哑变量与所有特征列。"""
    cols = design_columns(climate_features)
    work = df.dropna(subset=["Yield", *cols]).copy()
    tr = work[train_mask.reindex(work.index, fill_value=False)]
    X = sm.add_constant(tr[cols], has_constant="add")
    y = tr["Yield"].astype(float)
    res = sm.OLS(y, X, missing="raise").fit()
    test_idx = (work[test_mask.reindex(work.index, fill_value=False)].index
                if test_mask is not None else pd.Index([]))
    return FitResult(result=res, features=list(climate_features),
                     train_idx=tr.index, test_idx=test_idx)


def predict(fit: FitResult, df: pd.DataFrame, idx: pd.Index) -> pd.Series:
    cols = design_columns(fit.features)
    X = sm.add_constant(df.loc[idx, cols], has_constant="add")
    # 对齐训练期的列顺序 (含 const)
    X = X.reindex(columns=fit.result.params.index, fill_value=0.0)
    return pd.Series(fit.result.predict(X), index=idx)


def metrics(actual: pd.Series, pred: pd.Series) -> Dict[str, float]:
    a = actual.astype(float)
    p = pred.astype(float)
    err = a - p
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mae = float(np.mean(np.abs(err)))
    denom = float(np.sum((a - a.mean()) ** 2))
    r2 = float(1 - np.sum(err ** 2) / denom) if denom > 0 else float("nan")
    # 方向命中率: 相邻月环比方向是否一致
    if len(a) >= 2:
        da = np.sign(a.values[1:] - a.values[:-1])
        dp = np.sign(p.values[1:] - p.values[:-1])
        hit = float(np.mean(da == dp))
    else:
        hit = float("nan")
    mape = float(np.mean(np.abs(err / a.replace(0, np.nan)).dropna()) * 100)
    return {"rmse": rmse, "mae": mae, "r2_oos": r2, "dir_hit": hit, "mape": mape}


def date_mask(df: pd.DataFrame, start: str, end: str) -> pd.Series:
    return (df["Date"] >= start) & (df["Date"] <= end)
