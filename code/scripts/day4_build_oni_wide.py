# -*- coding: utf-8 -*-
"""
build_oni_wide.py
从 NOAA CPC 的 oni.ascii.txt 构建干净的 ONI「宽表」(wide table)。
- 输入：noaa_nino34_pacific_oni_raw.txt（列：SEAS 季节, YR 年份, TOTAL 海温, ANOM 距平=ONI 值）
- 输出：noaa_nino34_pacific_oni_wide.csv（行=Year，列=DJF..NDJ 共 12 个重叠三月季，值=ONI 距平 °C）
ANOM（anomaly，距平）即 ONI 值：Niño 3.4 海区 3 个月滚动 SST（海表温度）距平。
"""
import os
import pandas as pd

# 脚本位于 code/scripts/；气象原始数据在 data/raw/meteo/，处理后写入 data/processed/meteo/
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # 项目根 ONI project/
RAW = os.path.join(ROOT, "data", "raw", "meteo", "noaa_nino34_pacific_oni_raw.txt")
OUT_DIR = os.path.join(ROOT, "data", "processed", "meteo")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_WIDE = os.path.join(OUT_DIR, "noaa_nino34_pacific_oni_wide.csv")

# 12 个重叠三月季的标准顺序
SEASON_ORDER = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ",
                "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]

# 读取固定/空白分隔的 ascii 文件
try:
    raw = pd.read_csv(RAW, sep=r"\s+", engine="python")
except FileNotFoundError:
    raise SystemExit(f"[错误] 未找到 {RAW}，请先从 NOAA 下载 oni.ascii.txt。")
except Exception as e:
    raise SystemExit(f"[错误] 解析 ascii 失败：{e}")

# 字段校验，防止列名变化导致后续崩溃
expected = {"SEAS", "YR", "ANOM"}
if not expected.issubset(set(raw.columns)):
    raise SystemExit(f"[错误] 字段缺失，实际列为 {list(raw.columns)}，期望包含 {expected}")

raw["YR"] = pd.to_numeric(raw["YR"], errors="coerce")
raw["ANOM"] = pd.to_numeric(raw["ANOM"], errors="coerce")
raw = raw.dropna(subset=["YR", "SEAS"])
raw["YR"] = raw["YR"].astype(int)

# 透视成宽表：行=年份，列=季节
wide = raw.pivot_table(index="YR", columns="SEAS", values="ANOM", aggfunc="first")
# 按标准季节顺序排列列（只保留实际存在的）
wide = wide[[s for s in SEASON_ORDER if s in wide.columns]]
wide = wide.sort_index()
wide.index.name = "Year"
wide = wide.reset_index()

wide.to_csv(OUT_WIDE, index=False)

print(f"[OK] 已生成宽表：{OUT_WIDE}")
print(f"年份范围：{int(wide['Year'].min())} – {int(wide['Year'].max())}  "
      f"(共 {int(wide['Year'].max()) - int(wide['Year'].min()) + 1} 年)")
print(f"形状：{wide.shape[0]} 行 × {wide.shape[1]} 列")
print("前 3 行：")
print(wide.head(3).to_string(index=False))
