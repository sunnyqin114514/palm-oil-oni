import os
import pandas as pd

# 脚本位于 code/scripts/，气象原始数据位于 data/raw/meteo/
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # 项目根 ONI project/
CSV_FILE = os.path.join(ROOT, "data", "raw", "meteo", "malaysia_prcp.csv")

# ── 任务 1：读取 CSV 文件 ──
try:
    df = pd.read_csv(CSV_FILE)
except FileNotFoundError:
    raise SystemExit(f"[错误] 找不到文件：{os.path.abspath(CSV_FILE)}，请检查路径是否正确。")
except Exception as e:
    raise SystemExit(f"[错误] 读取 CSV 失败：{e}")

# ── 任务 2：打印前 5 行，确认 PRCP（降水）字段是否存在 ──
print("=" * 60)
print("【1】数据前 5 行：")
print(df.head())

if "PRCP" in df.columns:
    print("\n[OK] 已找到核心降水字段 'PRCP'。")
else:
    print("\n[警告] 未找到 'PRCP' 字段，当前列为：", list(df.columns))

# ── 任务 3：打印基本信息（行数、列数、字段类型）──
print("\n" + "=" * 60)
print("【2】数据基本结构：")
print(f"行数：{df.shape[0]}，列数：{df.shape[1]}")
print("\n字段类型与非空计数（df.info）：")
df.info()

# ── 任务 4：找到日期列并打印起止时间 ──
# ── 注意点 2：日期列名大小写不匹配 ──
# 标准列名是大写 'DATE'，但不同数据源可能是 'Date' / 'date'。
# 这里做大小写不敏感匹配，避免 KeyError。
print("\n" + "=" * 60)
print("【3】日期范围：")

date_col = next((c for c in df.columns if c.strip().lower() == "date"), None)

if date_col is None:
    print("[警告] 未找到日期列（DATE/Date/date），跳过日期范围检查。")
else:
    # ── 注意点 3：本数据 DATE 为 'YYYY-MM'（年-月）格式 ──
    # errors='coerce' 让无法解析的值变为 NaT，而不是直接报错
    dates = pd.to_datetime(df[date_col], errors="coerce")
    valid_dates = dates.dropna()
    if valid_dates.empty:
        print(f"[警告] 列 '{date_col}' 中没有可解析的日期。")
    else:
        print(f"日期列名：'{date_col}'")
        print(f"起始时间：{valid_dates.min().date()}")
        print(f"结束时间：{valid_dates.max().date()}")
        bad = dates.isna().sum()
        if bad > 0:
            print(f"[提示] 有 {bad} 行日期无法解析（已忽略）。")

# ── 任务 5：检查每一列的缺失值（NaN）数量 ──
print("\n" + "=" * 60)
print("【4】各列缺失值（NaN）统计：")
missing = df.isna().sum()
missing_pct = (missing / len(df) * 100).round(2) if len(df) > 0 else missing
summary = pd.DataFrame({"缺失数量": missing, "缺失占比(%)": missing_pct})
print(summary)

total_missing = int(missing.sum())
if total_missing == 0:
    print("\n[OK] 数据完整，无缺失值。")
else:
    print(f"\n[提示] 共发现 {total_missing} 个缺失值，请关注上述非零列。")
