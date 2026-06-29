# -*- coding: utf-8 -*-
"""
Explore and plot Yahoo Finance crude palm oil futures data.

Input:
    ../data/raw/product/CPO_F_daily_yahoo.csv

Outputs:
    ../data/figures/CPO_F_price_trend.png
    ../data/processed/product/CPO_F_calendar_gaps.csv

Checks:
    1. Basic structure and missing values
    2. Duplicated dates
    3. Large calendar gaps between adjacent trading dates
    4. Zero or negative price values
"""
from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # 项目根 ONI project/

RAW_FILE = os.path.join(ROOT, "data", "raw", "product", "CPO_F_daily_yahoo.csv")
FIGURE_DIR = os.path.join(ROOT, "data", "figures")
PROCESSED_DIR = os.path.join(ROOT, "data", "processed", "product")

os.makedirs(FIGURE_DIR, exist_ok=True)
os.makedirs(PROCESSED_DIR, exist_ok=True)

OUT_FIGURE = os.path.join(FIGURE_DIR, "CPO_F_price_trend.png")
OUT_GAPS = os.path.join(PROCESSED_DIR, "CPO_F_calendar_gaps.csv")

PRICE_COLUMNS = ["Open", "High", "Low", "Close", "Adj Close"]


def load_data() -> pd.DataFrame:
    """Load and validate the raw Yahoo Finance CSV."""
    try:
        df = pd.read_csv(RAW_FILE)
    except FileNotFoundError:
        raise SystemExit(f"[ERROR] File not found: {RAW_FILE}")
    except Exception as exc:
        raise SystemExit(f"[ERROR] Failed to read CSV: {exc}")

    required = ["Date", *PRICE_COLUMNS, "Volume"]
    missing_cols = [col for col in required if col not in df.columns]
    if missing_cols:
        raise SystemExit(f"[ERROR] Missing columns: {missing_cols}. Actual columns: {list(df.columns)}")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    for col in PRICE_COLUMNS + ["Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    return df


def find_large_calendar_gaps(df: pd.DataFrame, threshold_days: int = 7) -> pd.DataFrame:
    """Find adjacent trading-date gaps larger than threshold_days."""
    gaps = df[["Date"]].copy()
    gaps["Previous_Date"] = gaps["Date"].shift(1)
    gaps["Gap_Days"] = (gaps["Date"] - gaps["Previous_Date"]).dt.days
    gaps = gaps[gaps["Gap_Days"] > threshold_days].copy()
    gaps = gaps[["Previous_Date", "Date", "Gap_Days"]]
    gaps.to_csv(OUT_GAPS, index=False)
    return gaps


def print_checks(df: pd.DataFrame, gaps: pd.DataFrame) -> None:
    """Print concise data-quality checks."""
    start = df["Date"].min()
    end = df["Date"].max()
    span_years = (end - start).days / 365.25
    missing_counts = df.isna().sum()
    missing_rate = df[PRICE_COLUMNS].isna().mean().max()
    duplicated_dates = int(df["Date"].duplicated().sum())
    zero_or_negative = (df[PRICE_COLUMNS] <= 0).sum()

    print("=" * 70)
    print("CPO=F crude palm oil futures data check")
    print(f"Rows: {len(df)}")
    print(f"Date range: {start.date()} ~ {end.date()} ({span_years:.1f} years)")
    print(f"Max missing rate among price columns: {missing_rate:.2%}")
    print(f"Duplicated dates: {duplicated_dates}")

    print("\nMissing counts:")
    print(missing_counts.to_string())

    print("\nZero or negative price counts:")
    print(zero_or_negative.to_string())

    print("\nLarge calendar gaps (> 7 days between adjacent trading dates):")
    if gaps.empty:
        print("[OK] No large calendar gaps found.")
    else:
        print(gaps.to_string(index=False))
        print(f"[NOTE] Gap report saved to: {OUT_GAPS}")

    if int(zero_or_negative.sum()) == 0:
        print("\n[OK] No zero/negative price values found.")
    else:
        print("\n[WARNING] Zero/negative price values found. Please inspect before modeling.")


def plot_price_trend(df: pd.DataFrame, gaps: pd.DataFrame) -> None:
    """Plot Close price trend and mark large missing periods."""
    plt.figure(figsize=(14, 6))
    plt.plot(df["Date"], df["Close"], linewidth=1.1, color="#1f77b4", label="Close")

    for _, gap in gaps.iterrows():
        plt.axvspan(gap["Previous_Date"], gap["Date"], color="red", alpha=0.12)
        mid = gap["Previous_Date"] + (gap["Date"] - gap["Previous_Date"]) / 2
        ymax = df["Close"].max()
        plt.text(
            mid,
            ymax * 0.95,
            f"{int(gap['Gap_Days'])}d gap",
            ha="center",
            va="top",
            color="red",
            fontsize=9,
        )

    plt.title("CPO=F Crude Palm Oil Futures Daily Close Price")
    plt.xlabel("Date")
    plt.ylabel("Price")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT_FIGURE, dpi=160)
    print(f"\n[OK] Price trend chart saved to: {OUT_FIGURE}")


def main() -> None:
    df = load_data()
    gaps = find_large_calendar_gaps(df)
    print_checks(df, gaps)
    plot_price_trend(df, gaps)


if __name__ == "__main__":
    main()
