# -*- coding: utf-8 -*-
"""为温度研究 + 三维模型构建全部候选特征 (滚动窗口/非对称/三区空间交互)。

滚动从 2007 起算 (气象数据 2007-2026-05), 再裁剪到建模窗口 2010-01~2026-05,
避免因 rolling 损失 2010 年早期行。

候选特征命名:
  全国:   TAVG_DEV_{w}m, PRCP_DEV_{w}m        (w 月滚动距平, 即"积温/积水"窗口)
          TAVG_HEAT_{w}m = max(TAVG_DEV_{w}m,0)  偏热部分
          TAVG_COLD_{w}m = min(TAVG_DEV_{w}m,0)  偏冷部分 (<=0)
  分区 R∈{West,Sarawak,Sabah}:
          T2M_DEV_{R}_{w}m, PRCP_DEV_{R}_{w}m
          INTX_{R}_{w}m   = T2M_DEV_{R}_{w}m * PRCP_DEV_{R}_{w}m       (温降交互)
          HOTDRY_{R}_{w}m = max(T2M_DEV,0)*max(-PRCP_DEV,0) (>=0)      又热又旱复合胁迫
  全国交互: INTX_NAT_{w}m, HOTDRY_NAT_{w}m
  三区合成: HOTDRY_ALL_{w}m = 三区 HOTDRY 之和 (区域复合胁迫总量)
"""
from __future__ import annotations

from pathlib import Path
from typing import List

import numpy as np
import pandas as pd

from build_extended_dataset import (
    REGIONS,
    read_national_weather,
    read_regional,
    OUT_CSV as EXTENDED_CSV,
)

WINDOWS = list(range(1, 13))


def _roll(s: pd.Series, w: int) -> pd.Series:
    return s.astype(float) if w <= 1 else s.rolling(window=w, min_periods=w).mean()


def build_features() -> pd.DataFrame:
    # 2007 起算的气象距平 (全国 + 分区)
    nat = read_national_weather()[["Date", "TAVG_DEV", "PRCP_DEV"]].sort_values("Date").reset_index(drop=True)
    reg = read_regional().sort_values("Date").reset_index(drop=True)

    feat = nat.merge(reg, on="Date", how="left")
    new_cols: dict[str, pd.Series] = {}
    for w in WINDOWS:
        tavg_w = _roll(nat["TAVG_DEV"], w)
        prcp_w = _roll(nat["PRCP_DEV"], w)
        new_cols[f"TAVG_DEV_{w}m"] = tavg_w
        new_cols[f"PRCP_DEV_{w}m"] = prcp_w
        new_cols[f"TAVG_HEAT_{w}m"] = tavg_w.clip(lower=0)
        new_cols[f"TAVG_COLD_{w}m"] = tavg_w.clip(upper=0)
        new_cols[f"INTX_NAT_{w}m"] = tavg_w * prcp_w
        new_cols[f"HOTDRY_NAT_{w}m"] = tavg_w.clip(lower=0) * (-prcp_w).clip(lower=0)

    for R in REGIONS:
        for w in WINDOWS:
            tw = _roll(feat[f"T2M_DEV_{R}"], w)
            pw = _roll(feat[f"PRCP_DEV_{R}"], w)
            new_cols[f"T2M_DEV_{R}_{w}m"] = tw
            new_cols[f"PRCP_DEV_{R}_{w}m"] = pw
            new_cols[f"INTX_{R}_{w}m"] = tw * pw
            new_cols[f"HOTDRY_{R}_{w}m"] = tw.clip(lower=0) * (-pw).clip(lower=0)
    for w in WINDOWS:
        new_cols[f"HOTDRY_ALL_{w}m"] = sum(new_cols[f"HOTDRY_{R}_{w}m"] for R in REGIONS)

    feat = pd.concat([feat, pd.DataFrame(new_cols, index=feat.index)], axis=1)

    # 合并到扩展数据集 (Yield/Trend/Month/ONI_lag12/Area_Source 等)
    base = pd.read_csv(EXTENDED_CSV)
    drop_dupe = [c for c in ["TAVG_DEV", "PRCP_DEV"] if c in feat.columns]
    merged = base.merge(feat.drop(columns=[]), on="Date", how="left", suffixes=("", "_feat"))
    merged = merged[merged.Date >= "2010-01"].sort_values("Date").reset_index(drop=True)
    return merged


if __name__ == "__main__":
    df = build_features()
    out = Path(EXTENDED_CSV).parent / "palm_oil_features.csv"
    df.to_csv(out, index=False)
    print(f"[ok] 特征表 {df.shape[0]} 行 x {df.shape[1]} 列 -> {out}")
    cols = [c for c in df.columns if any(k in c for k in ["TAVG_DEV_3m", "HOTDRY_ALL_3m", "INTX_West_3m"])]
    print("[示例列]", cols)
    print(df[df.Year == 2026][["Date"] + cols].to_string(index=False))
