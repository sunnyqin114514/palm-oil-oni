# -*- coding: utf-8 -*-
"""
Download crude palm oil futures prices from Yahoo Finance.

Target symbol:
    CPO=F  (Crude Palm Oil Futures on Yahoo Finance)

Output:
    ../data/raw/product/CPO_F_daily_yahoo.csv

The script validates:
    1. Time span >= 10 years
    2. Missing-rate <= 5%
"""
from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd


SYMBOL = "CPO=F"
INTERVAL = "1d"
START_DATE = "2014-01-01"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))  # 项目根 ONI project/
RAW_DIR = os.path.join(ROOT, "data", "raw", "product")
os.makedirs(RAW_DIR, exist_ok=True)
OUT_CSV = os.path.join(RAW_DIR, "CPO_F_daily_yahoo.csv")


def to_unix_seconds(date_text: str) -> int:
    """Convert YYYY-MM-DD to Unix timestamp seconds in UTC."""
    dt = datetime.strptime(date_text, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def fetch_yahoo_chart(symbol: str, start_date: str, interval: str) -> dict:
    """Fetch Yahoo Finance chart JSON using the public query endpoint."""
    period1 = to_unix_seconds(start_date)
    # Yahoo's period2 is exclusive; using now + 1 day avoids missing today's bar.
    period2 = int(time.time()) + 24 * 60 * 60
    encoded_symbol = urllib.parse.quote(symbol, safe="")
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded_symbol}"
        f"?period1={period1}&period2={period2}&interval={interval}"
        "&events=history&includeAdjustedClose=true"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            )
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            payload = resp.read().decode("utf-8")
    except Exception as exc:
        raise SystemExit(f"[ERROR] Failed to download Yahoo Finance data: {exc}")
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"[ERROR] Yahoo response is not valid JSON: {exc}")


def parse_chart_to_dataframe(data: dict) -> pd.DataFrame:
    """Convert Yahoo chart JSON into a clean price DataFrame."""
    chart = data.get("chart", {})
    error = chart.get("error")
    if error:
        raise SystemExit(f"[ERROR] Yahoo returned error: {error}")
    result = chart.get("result") or []
    if not result:
        raise SystemExit("[ERROR] Yahoo returned no result data.")

    item = result[0]
    timestamps = item.get("timestamp") or []
    quote = ((item.get("indicators") or {}).get("quote") or [{}])[0]
    adjclose = ((item.get("indicators") or {}).get("adjclose") or [{}])[0]

    if not timestamps:
        raise SystemExit("[ERROR] Yahoo returned no timestamps.")

    df = pd.DataFrame(
        {
            "Date": pd.to_datetime(timestamps, unit="s", utc=True).date,
            "Open": quote.get("open"),
            "High": quote.get("high"),
            "Low": quote.get("low"),
            "Close": quote.get("close"),
            "Adj Close": adjclose.get("adjclose"),
            "Volume": quote.get("volume"),
        }
    )
    df["Date"] = pd.to_datetime(df["Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    return df


def validate(df: pd.DataFrame) -> None:
    """Print basic validation for the Day 5 data requirement."""
    if df.empty:
        raise SystemExit("[ERROR] Downloaded DataFrame is empty.")

    start = df["Date"].min()
    end = df["Date"].max()
    span_years = (end - start).days / 365.25
    missing_rate = df[["Open", "High", "Low", "Close", "Adj Close"]].isna().mean().max()

    print("=" * 60)
    print("Yahoo Finance download summary")
    print(f"Symbol: {SYMBOL}")
    print(f"Interval: {INTERVAL}")
    print(f"Rows: {len(df)}")
    print(f"Date range: {start.date()} ~ {end.date()} ({span_years:.1f} years)")
    print(f"Max missing rate among price columns: {missing_rate:.2%}")
    print(f"Output CSV: {OUT_CSV}")

    print("\nHead(5):")
    print(df.head(5).to_string(index=False))
    print("\nMissing counts:")
    print(df.isna().sum().to_string())

    if span_years < 10:
        print("\n[WARNING] Time span is less than 10 years.")
    else:
        print("\n[OK] Time span requirement met: >= 10 years.")

    if missing_rate > 0.05:
        print("[WARNING] Missing-rate requirement not met: > 5%.")
    else:
        print("[OK] Missing-rate requirement met: <= 5%.")


def fetch_yfinance_dataframe(symbol: str, start_date: str, interval: str) -> pd.DataFrame:
    """Download data through yfinance, which handles Yahoo cookie/crumb details."""
    try:
        import yfinance as yf
    except ImportError as exc:
        raise RuntimeError("yfinance is not installed. Run: python3 -m pip install yfinance") from exc

    try:
        df = yf.download(
            symbol,
            start=start_date,
            interval=interval,
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as exc:
        raise RuntimeError(f"yfinance download failed: {exc}") from exc

    if df.empty:
        raise RuntimeError("yfinance returned an empty DataFrame.")

    # yfinance can return MultiIndex columns in newer versions; flatten if needed.
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [col[0] for col in df.columns]

    df = df.reset_index()
    df["Date"] = pd.to_datetime(df["Date"]).dt.tz_localize(None)
    expected = ["Date", "Open", "High", "Low", "Close", "Adj Close", "Volume"]
    missing_cols = [col for col in expected if col not in df.columns]
    if missing_cols:
        raise RuntimeError(f"yfinance output missing columns: {missing_cols}")
    return df[expected].sort_values("Date").reset_index(drop=True)


def main() -> None:
    try:
        df = fetch_yfinance_dataframe(SYMBOL, START_DATE, INTERVAL)
        print("[OK] Download method: yfinance")
    except Exception as exc:
        print(f"[WARNING] yfinance failed, falling back to Yahoo chart API: {exc}")
        data = fetch_yahoo_chart(SYMBOL, START_DATE, INTERVAL)
        df = parse_chart_to_dataframe(data)
        print("[OK] Download method: Yahoo chart API")

    df.to_csv(OUT_CSV, index=False)
    validate(df)


if __name__ == "__main__":
    main()
