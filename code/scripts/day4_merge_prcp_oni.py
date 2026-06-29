# -*- coding: utf-8 -*-
"""
merge_prcp_oni.py
1) 把 malaysia_prcp.csv 的 2 个站点（KLIA + Sultan Abdul Aziz Shah）按月取
   区域平均 (regional average)，合成单条降水序列。
2) 与 noaa_nino34_pacific_oni_monthly.csv（ONI 月度长表）按 DATE 内连接合并。
3) 输出 malaysia_prcp_regional.csv 与吉隆坡降水 × Niño 3.4 ONI 合并表，并打印对齐汇总。
"""
import os
import pandas as pd

# 脚本位于 code/scripts/；气象原始数据在 data/raw/meteo/，派生数据写到 data/processed/meteo/
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # 项目根 ONI project/
PRCP_FILE = os.path.join(ROOT, "data", "raw", "meteo", "malaysia_prcp.csv")
ONI_LONG_FILE = os.path.join(
    ROOT, "data", "processed", "meteo", "noaa_nino34_pacific_oni_monthly.csv"
)
OUT_DIR = os.path.join(ROOT, "data", "processed", "meteo")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_REGIONAL = os.path.join(OUT_DIR, "malaysia_prcp_regional.csv")
OUT_MERGED = os.path.join(
    OUT_DIR, "kuala_lumpur_malaysia_prcp_noaa_nino34_pacific_oni_merged.csv"
)

# ── 读取（带兜底）──
try:
    prcp = pd.read_csv(PRCP_FILE)
    oni_long = pd.read_csv(ONI_LONG_FILE)
except FileNotFoundError as e:
    raise SystemExit(f"[错误] 缺少输入文件：{e}")

# ── 字段校验 ──
for col in ("DATE", "PRCP", "STATION"):
    if col not in prcp.columns:
        raise SystemExit(f"[错误] 降水文件缺列 {col}，实际列：{list(prcp.columns)}")
for col in ("DATE", "ONI_Value"):
    if col not in oni_long.columns:
        raise SystemExit(f"[错误] ONI 长表缺列 {col}，实际列：{list(oni_long.columns)}")

# 统一 DATE 为 YYYY-MM 字符串（与 ONI 长表一致）
prcp["DATE"] = pd.to_datetime(prcp["DATE"], errors="coerce").dt.strftime("%Y-%m")
prcp["PRCP"] = pd.to_numeric(prcp["PRCP"], errors="coerce")
prcp = prcp.dropna(subset=["DATE", "PRCP"])

# ── 区域平均：按月对所有站点取均值 ──
n_stations = prcp["STATION"].nunique()
station_count_by_month = prcp.groupby("DATE")["STATION"].nunique()

regional = (
    prcp.groupby("DATE", as_index=False)
        .agg(PRCP=("PRCP", "mean"),
             STATION_COUNT=("STATION", "nunique"))
        .sort_values("DATE")
        .reset_index(drop=True)
)
regional.to_csv(OUT_REGIONAL, index=False)

# ── 合并 (inner join on DATE) ──
merged = regional.merge(oni_long, on="DATE", how="inner").sort_values("DATE").reset_index(drop=True)
merged.to_csv(OUT_MERGED, index=False)

# ── 打印汇总 ──
print("=" * 60)
print("【区域平均】")
print(f"原始降水：{len(prcp)} 行 × {n_stations} 站点")
print(f"按月取站点均值后：{len(regional)} 行（去重月份）")
print(f"  - 单站月份数：{(station_count_by_month == 1).sum()}")
print(f"  - 双站月份数（已平均）：{(station_count_by_month == 2).sum()}")
print(f"区域平均文件：{OUT_REGIONAL}")
print(f"PRCP 范围：min={regional['PRCP'].min():.2f}, max={regional['PRCP'].max():.2f}, mean={regional['PRCP'].mean():.2f}")

print("\n" + "=" * 60)
print("【合并 (regional PRCP × ONI long, inner join on DATE)】")
print(f"合并结果：{merged.shape[0]} 行 × {merged.shape[1]} 列")
print(f"时间范围：{merged['DATE'].min()} ~ {merged['DATE'].max()}")
print(f"列：{list(merged.columns)}")
print(f"缺失值合计：{int(merged.isna().sum().sum())}")
print(f"合并文件：{OUT_MERGED}")
print("\n合并 head(5)：")
print(merged.head(5).to_string(index=False))
