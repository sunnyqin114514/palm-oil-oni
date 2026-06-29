import os
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 无界面后端，纯保存图片，避免在无显示环境报错
import matplotlib.pyplot as plt

# 脚本位于 code/scripts/；输入数据在 data/raw/meteo/，输出图保存到 data/figures/
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # 项目根 ONI project/
CSV_FILE = os.path.join(ROOT, "data", "raw", "meteo", "malaysia_prcp.csv")
OUT_DIR = os.path.join(ROOT, "data", "figures")
os.makedirs(OUT_DIR, exist_ok=True)
OUT_FILE = os.path.join(OUT_DIR, "prcp_trend.png")

# ── 读取数据（带兜底）──
try:
    df = pd.read_csv(CSV_FILE)
except FileNotFoundError:
    raise SystemExit(f"[错误] 找不到文件：{os.path.abspath(CSV_FILE)}")
except Exception as e:
    raise SystemExit(f"[错误] 读取 CSV 失败：{e}")

# ── 日期列大小写不敏感匹配，避免 KeyError ──
date_col = next((c for c in df.columns if c.strip().lower() == "date"), None)
if date_col is None:
    raise SystemExit("[错误] 未找到日期列（DATE/Date/date）。")
if "PRCP" not in df.columns:
    raise SystemExit("[错误] 未找到 PRCP 字段。")

# DATE 为 'YYYY-MM'，转成日期类型；PRCP 显式转数值防止字符串混入
df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
df["PRCP"] = pd.to_numeric(df["PRCP"], errors="coerce")

# 按时间排序，丢弃无法解析的行
df = df.dropna(subset=[date_col, "PRCP"]).sort_values(date_col)

# ── 绘图（标签用英文，避免 matplotlib 默认字体无法渲染中文导致乱码）──
plt.figure(figsize=(14, 6))
plt.plot(df[date_col], df["PRCP"], color="#1f77b4", linewidth=1.2, label="PRCP")

# 标注最大/最小值点
imax = df["PRCP"].idxmax()
imin = df["PRCP"].idxmin()
plt.scatter([df.loc[imax, date_col]], [df.loc[imax, "PRCP"]], color="red", zorder=5)
plt.scatter([df.loc[imin, date_col]], [df.loc[imin, "PRCP"]], color="green", zorder=5)
plt.annotate(f"max {df.loc[imax, 'PRCP']:.1f}",
             (df.loc[imax, date_col], df.loc[imax, "PRCP"]),
             textcoords="offset points", xytext=(0, 8), color="red", fontsize=9)
plt.annotate(f"min {df.loc[imin, 'PRCP']:.1f}",
             (df.loc[imin, date_col], df.loc[imin, "PRCP"]),
             textcoords="offset points", xytext=(0, -14), color="green", fontsize=9)

start = df[date_col].min().date()
end = df[date_col].max().date()
plt.title(f"Malaysia (Kuala Lumpur Intl) Monthly Precipitation  {start} ~ {end}")
plt.xlabel("Date")
plt.ylabel("PRCP (monthly precipitation)")
plt.grid(True, alpha=0.3)
plt.legend()
plt.tight_layout()

plt.savefig(OUT_FILE, dpi=150)
print(f"[OK] 图表已保存：{os.path.abspath(OUT_FILE)}")
print(f"数据点数：{len(df)}，时间范围：{start} ~ {end}")
print(f"PRCP 范围：min={df['PRCP'].min():.2f}, max={df['PRCP'].max():.2f}, mean={df['PRCP'].mean():.2f}")
