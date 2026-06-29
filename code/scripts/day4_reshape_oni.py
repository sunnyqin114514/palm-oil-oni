# -*- coding: utf-8 -*-
"""
reshape_oni.py
把 ONI「宽表」(wide table) 用 pandas.melt() 转换为「长表」(long/tidy table)，
结构与降水数据一致：DATE (YYYY-MM) + ONI_Value，便于后续时间轴对齐与滞后期分析。

宽表：行=Year，列=DJF..NDJ（12 个重叠三月季），值=ONI 距平 °C。
长表：每行一个月，DATE=YYYY-MM，ONI_Value=该月对应季的 ONI 值。

季→月映射约定：ONI 是 3 个月滚动季，按「中心月」(center month) 落到具体月份。
例如 DJF(Dec-Jan-Feb) 中心月=1 月；JFM 中心月=2 月；... NDJ(Nov-Dec-Jan) 中心月=12 月。
"""
import os
import pandas as pd

# 脚本位于 code/scripts/；气象数据位于 data/raw/meteo/ 与 data/processed/meteo/
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # 项目根 ONI project/
IN_WIDE = os.path.join(ROOT, "data", "processed", "meteo", "noaa_nino34_pacific_oni_wide.csv")
OUT_DIR = os.path.join(ROOT, "data", "processed", "meteo")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_LONG = os.path.join(OUT_DIR, "noaa_nino34_pacific_oni_monthly.csv")
PRCP_FILE = os.path.join(ROOT, "data", "raw", "meteo", "malaysia_prcp.csv")

# 季节 -> 中心月（1..12）
SEASON_TO_MONTH = {
    "DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
    "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12,
}

# ── 读取宽表（带兜底）──
try:
    wide = pd.read_csv(IN_WIDE)
except FileNotFoundError:
    raise SystemExit(f"[错误] 未找到宽表 {IN_WIDE}，请先运行 build_oni_wide.py。")
except Exception as e:
    raise SystemExit(f"[错误] 读取宽表失败：{e}")

if "Year" not in wide.columns:
    raise SystemExit(f"[错误] 宽表缺少 'Year' 列，实际列为 {list(wide.columns)}")

# ── 核心：pandas.melt() 宽 → 长 ──
season_cols = [c for c in wide.columns if c in SEASON_TO_MONTH]
long = wide.melt(
    id_vars="Year",
    value_vars=season_cols,
    var_name="Season",       # 季节名（DJF..NDJ）
    value_name="ONI_Value",  # ONI 距平值
)

# ── 季 → 中心月 → DATE(YYYY-MM) ──
long["Month"] = long["Season"].map(SEASON_TO_MONTH)
# 显式数值化，防止字符串混入导致比较/排序异常
long["Year"] = pd.to_numeric(long["Year"], errors="coerce").astype("Int64")
long["ONI_Value"] = pd.to_numeric(long["ONI_Value"], errors="coerce")

# 丢弃尚未发布的月份（当前年份后续季为空，属正常情况）
long = long.dropna(subset=["Year", "Month", "ONI_Value"])

# 统一时间戳为每月 1 号，再格式化成 YYYY-MM 字符串（与降水数据一致）
long["DATE"] = pd.to_datetime(
    dict(year=long["Year"].astype(int), month=long["Month"].astype(int), day=1)
)
long = long.sort_values("DATE").reset_index(drop=True)
long["DATE"] = long["DATE"].dt.strftime("%Y-%m")

# 只保留与降水一致的两列
long_out = long[["DATE", "ONI_Value"]].copy()
long_out.to_csv(OUT_LONG, index=False)

# ── 校验与对齐报告 ──
print("=" * 60)
print(f"[OK] 已生成长表：{OUT_LONG}")
print(f"长表形状：{long_out.shape[0]} 行 × {long_out.shape[1]} 列")
print(f"ONI 时间范围：{long_out['DATE'].min()} ~ {long_out['DATE'].max()}")
print(f"缺失值：DATE={long_out['DATE'].isna().sum()}, ONI_Value={long_out['ONI_Value'].isna().sum()}")
print("\n长表 head(5)：")
print(long_out.head(5).to_string(index=False))

# 与降水时间轴对齐检查
try:
    prcp = pd.read_csv(PRCP_FILE)
    prcp_dates = set(pd.to_datetime(prcp["DATE"], errors="coerce").dt.strftime("%Y-%m"))
    oni_dates = set(long_out["DATE"])
    overlap = sorted(prcp_dates & oni_dates)
    print("\n" + "=" * 60)
    print("【时间轴对齐检查（与 malaysia_prcp.csv）】")
    print(f"降水月份数：{len(prcp_dates)}，ONI 月份数：{len(oni_dates)}")
    print(f"可对齐重叠月份数：{len(overlap)}")
    if overlap:
        print(f"重叠区间：{overlap[0]} ~ {overlap[-1]}")
except FileNotFoundError:
    print("\n[提示] 未找到降水文件，跳过对齐检查。")
except Exception as e:
    print(f"\n[提示] 对齐检查出错（已跳过）：{e}")
