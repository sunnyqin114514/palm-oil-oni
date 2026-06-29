# -*- coding: utf-8 -*-
"""day13_verify_excel_archives.py — 严格比对源文件 vs 打包后的 Excel sheet。

每个被打包的源文件必须满足:
  - 行数完全一致
  - 关键数值列的 sum / min / max 完全一致
"""
from __future__ import annotations

import sys
from io import StringIO
from pathlib import Path
from typing import Any, List

import pandas as pd
from numbers_parser import Document as NumbersDoc

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA = PROJECT_ROOT / "data"
ARC = DATA / "processed" / "archives"

FAILED: List[str] = []
PASSED: List[str] = []


def check(name: str, lhs: Any, rhs: Any) -> None:
    if isinstance(lhs, float) and isinstance(rhs, float):
        ok = abs(lhs - rhs) <= abs(lhs) * 1e-6 + 1e-6
    else:
        ok = lhs == rhs
    label = f"{name}: src={lhs!r}  excel={rhs!r}"
    (PASSED if ok else FAILED).append(label)


def read_sheet(path: Path, sheet: str) -> pd.DataFrame:
    return pd.read_excel(path, sheet_name=sheet)


def src_daily_csv(path: Path) -> pd.DataFrame:
    with open(path) as f:
        lines = f.readlines()
    return pd.read_csv(StringIO("".join(lines[2:])))


def src_numbers(path: Path, header_row_index: int = 1) -> pd.DataFrame:
    doc = NumbersDoc(str(path))
    table = doc.sheets[0].tables[0]
    raw = [[c.value for c in r] for r in table.rows()]
    cols = [str(c) if c is not None else f"col_{i}" for i, c in enumerate(raw[header_row_index])]
    return pd.DataFrame(raw[header_row_index + 1:], columns=cols)


def src_noaa_ascii() -> pd.DataFrame:
    rows = []
    with open(DATA / "raw" / "meteo" / "noaa_nino34_pacific_oni_raw.txt") as f:
        next(f)
        for line in f:
            parts = line.split()
            if len(parts) == 4:
                rows.append((parts[0], int(parts[1]), float(parts[2]), float(parts[3])))
    return pd.DataFrame(rows, columns=["SEAS", "YR", "SST_TOTAL_C", "ONI_ANOM_C"])


def verify_excel1() -> None:
    p = ARC / "01_palm_oil_planted_area_malaysia.xlsx"
    
    # Check MPOB mature area
    src_mpob = pd.read_csv(DATA / "raw" / "product" / "mpob_palm_oil_planted_area_mature.csv")
    e_mpob = read_sheet(p, "01_MPOB_Mature_Area")
    check("[1] MPOB rows", len(src_mpob), len(e_mpob))
    check("[1] MPOB Mature sum", float(src_mpob["MATURE_HECTARES"].sum()), float(e_mpob["MATURE_HECTARES"].sum()))
    check("[1] MPOB Total sum", float(src_mpob["TOTAL_HECTARES"].sum()), float(e_mpob["TOTAL_HECTARES"].sum()))
    
    # Check iFinD area
    src_ifind = pd.read_csv(DATA / "raw" / "product" / "ifind_edb_palm_oil_planted_area_my.csv")
    e_ifind = read_sheet(p, "02_Planted_Area_iFinD")
    check("[1] iFinD rows", len(src_ifind), len(e_ifind))
    check("[1] iFinD VALUE sum", float(src_ifind["VALUE"].sum()), float(e_ifind["VALUE"].sum()))
    check("[1] iFinD VALUE min", float(src_ifind["VALUE"].min()), float(e_ifind["VALUE"].min()))
    check("[1] iFinD VALUE max", float(src_ifind["VALUE"].max()), float(e_ifind["VALUE"].max()))


def verify_excel2() -> None:
    p = ARC / "02_climate_data_malaysia.xlsx"
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from day13_pack_excel_archives import (
        _read_ecmwf_seasonal_grid_csv,
        _read_historical_prcp,
        _read_historical_tavg,
        _read_oni_monthly_long,
    )

    # 01 Malaysia Historical PRCP
    s = _read_historical_prcp()
    e = read_sheet(p, "01_MY_PRCP_History")
    check("[2.01] PRCP rows", len(s), len(e))
    check("[2.01] PRCP sum", float(s["PRCP"].sum()), float(e["PRCP"].sum()))
    check("[2.01] PRCP min YM", str(s["YM"].min()), str(e["YM"].min()))
    check("[2.01] PRCP max YM", str(s["YM"].max()), str(e["YM"].max()))

    # 02 Malaysia Historical TAVG
    s = _read_historical_tavg()
    e = read_sheet(p, "02_MY_TAVG_History")
    check("[2.02] TAVG rows", len(s), len(e))
    check("[2.02] TAVG sum", float(s["TAVG_C"].sum()), float(e["TAVG_C"].sum()))
    check("[2.02] TAVG min YM", str(s["YM"].min()), str(e["YM"].min()))
    check("[2.02] TAVG max YM", str(s["YM"].max()), str(e["YM"].max()))

    # 03 ONI Monthly
    s = _read_oni_monthly_long()
    e = read_sheet(p, "03_ONI_Monthly")
    check("[2.03] ONI rows", len(s), len(e))
    check("[2.03] ONI sum", float(s["ONI"].sum()), float(e["ONI"].sum()))
    check("[2.03] ONI min", float(s["ONI"].min()), float(e["ONI"].min()))
    check("[2.03] ONI max", float(s["ONI"].max()), float(e["ONI"].max()))

    # 04 Malaysia Climate Forecast
    s = _read_ecmwf_seasonal_grid_csv()
    e = read_sheet(p, "04_MY_Climate_Forecast")
    check("[2.04] Forecast rows", len(s), len(e))
    check("[2.04] Forecast T2M sum", float(s["T2M_C"].sum()), float(e["T2M_C"].sum()))
    check("[2.04] Forecast PRCP sum", float(s["PRCP_MM_PER_MONTH"].sum()), float(e["PRCP_MM_PER_MONTH"].sum()))
    check("[2.04] Forecast target YM", str(s["TARGET_YM"].min()), str(e["TARGET_YM"].min()))


def verify_excel3() -> None:
    p = ARC / "03_palm_oil_production_malaysia.xlsx"
    src = pd.read_csv(DATA / "raw" / "product" / "ifind_edb_palm_oil_production_my.csv")
    e = read_sheet(p, "Production_Monthly_iFinD")
    check("[3] rows", len(src), len(e))
    check("[3] VALUE sum", float(src["VALUE"].sum()), float(e["VALUE"].sum()))
    check("[3] VALUE min", float(src["VALUE"].min()), float(e["VALUE"].min()))
    check("[3] VALUE max", float(src["VALUE"].max()), float(e["VALUE"].max()))
    check("[3] DATE min", str(src["DATE"].min()), str(e["DATE"].min()))
    check("[3] DATE max", str(src["DATE"].max()), str(e["DATE"].max()))


def main() -> None:
    verify_excel1()
    verify_excel2()
    verify_excel3()
    print("\n──────── 校验通过 ────────")
    for line in PASSED:
        print("  ✓", line)
    if FAILED:
        print("\n──────── 校验失败 ────────")
        for line in FAILED:
            print("  ✗", line)
        sys.exit(1)
    print(f"\n全部 {len(PASSED)} 项校验通过 ✓")


if __name__ == "__main__":
    main()
