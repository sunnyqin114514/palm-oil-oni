# -*- coding: utf-8 -*-
"""构建马来西亚三大棕榈油产区的月度气温/降水序列 (陆地格点掩膜)。

输入:
  data/processed/meteo/nasa_power_grid_full_malaysia_monthly.csv
    (由 code/scripts/fetch_nasa_power_full_malaysia.py 生成, 含婆罗洲, 到 2026-05)

三区定义 (经纬度框 + global_land_mask 陆地判定):
  - West   西马半岛:        lon [99.5, 104.75], lat [1.0, 7.0]
  - Sarawak 砂拉越(西北婆罗洲带): lon [109.5, 115.3], lat [0.8, 5.0]
  - Sabah  沙巴(东北婆罗洲带):    lon [115.3, 119.5], lat [4.0, 7.5]
  说明: 婆罗洲两区的框可能含极少量邻近非马来西亚陆地格点, 但代表该种植带的区域气候;
        统计的是区域气候差异而非精确行政边界。

各区聚合: 该区所有陆地格点的简单平均 (T2M 月均 °C, PRCP 月总 mm)。
气候常态: 同日历月在 2007-2025 上的均值 (与全国口径一致, 不含 2026 以免污染基准)。

输出:
  data/processed/meteo/malaysia_regional_weather_monthly.csv
    长表: Date, Region, T2M, PRCP, T2M_CLIM, PRCP_CLIM, T2M_DEV, PRCP_DEV, n_cells
  data/processed/meteo/malaysia_regional_weather_wide.csv
    宽表: Date + 各区 T2M_<R>/PRCP_<R>/T2M_DEV_<R>/PRCP_DEV_<R> + 全国 T2M_NAT/PRCP_NAT/*_DEV
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Tuple

import pandas as pd
from global_land_mask import globe

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
GRID_CSV = PROJECT_ROOT / "data" / "processed" / "meteo" / "nasa_power_grid_full_malaysia_monthly.csv"
OUT_LONG = PROJECT_ROOT / "data" / "processed" / "meteo" / "malaysia_regional_weather_monthly.csv"
OUT_WIDE = PROJECT_ROOT / "data" / "processed" / "meteo" / "malaysia_regional_weather_wide.csv"

# Region -> (lon_min, lon_max, lat_min, lat_max)
REGION_BOXES: Dict[str, Tuple[float, float, float, float]] = {
    "West": (99.5, 104.75, 1.0, 7.0),
    "Sarawak": (109.5, 115.3, 0.8, 5.0),
    "Sabah": (115.3, 119.5, 4.0, 7.5),
}
# 全国参考框 (与历史 NASA POWER Regional 国家序列完全一致的口径)
NAT_BOX = (100.0, 109.375, 1.0, 6.5)

CLIM_END = "2025-12"  # 气候常态基准只用 2007-2025


def assign_region(lat: float, lon: float) -> str | None:
    if not bool(globe.is_land(lat, lon)):
        return None
    for region, (lo, hi, la, ha) in REGION_BOXES.items():
        if lo <= lon <= hi and la <= lat <= ha:
            return region
    return None


def build() -> None:
    grid = pd.read_csv(GRID_CSV)
    cells = grid[["LAT", "LON"]].drop_duplicates().copy()
    cells["Region"] = [assign_region(la, lo) for la, lo in zip(cells["LAT"], cells["LON"])]

    counts = cells["Region"].value_counts(dropna=False).to_dict()
    print("[cells] 各区陆地格点数:", {k: v for k, v in counts.items()})

    grid = grid.merge(cells, on=["LAT", "LON"], how="left")

    # ---- 区域长表聚合 ----
    reg = grid.dropna(subset=["Region"]).copy()
    region_monthly = (
        reg.groupby(["Date", "Region"], as_index=False)
        .agg(T2M=("T2M", "mean"), PRCP=("PRCP", "mean"), n_cells=("T2M", "size"))
    )
    region_monthly["Month"] = pd.to_datetime(region_monthly["Date"]).dt.month

    clim_src = region_monthly[region_monthly["Date"] <= CLIM_END]
    clim = (clim_src.groupby(["Region", "Month"], as_index=False)
            .agg(T2M_CLIM=("T2M", "mean"), PRCP_CLIM=("PRCP", "mean")))
    region_monthly = region_monthly.merge(clim, on=["Region", "Month"], how="left")
    region_monthly["T2M_DEV"] = region_monthly["T2M"] - region_monthly["T2M_CLIM"]
    region_monthly["PRCP_DEV"] = region_monthly["PRCP"] - region_monthly["PRCP_CLIM"]
    region_monthly = region_monthly.sort_values(["Date", "Region"]).reset_index(drop=True)
    region_monthly.to_csv(OUT_LONG, index=False)
    print(f"[ok] 区域长表 {len(region_monthly)} 行 -> {OUT_LONG.name}")

    # ---- 全国参考 (老框均值) ----
    lo, hi, la, ha = NAT_BOX
    nat_cells = grid[(grid.LON >= lo) & (grid.LON <= hi) & (grid.LAT >= la) & (grid.LAT <= ha)]
    nat = (nat_cells.groupby("Date", as_index=False)
           .agg(T2M_NAT=("T2M", "mean"), PRCP_NAT=("PRCP", "mean")))
    nat["Month"] = pd.to_datetime(nat["Date"]).dt.month
    nat_clim = (nat[nat.Date <= CLIM_END].groupby("Month", as_index=False)
                .agg(T2M_NAT_CLIM=("T2M_NAT", "mean"), PRCP_NAT_CLIM=("PRCP_NAT", "mean")))
    nat = nat.merge(nat_clim, on="Month", how="left")
    nat["T2M_DEV_NAT"] = nat["T2M_NAT"] - nat["T2M_NAT_CLIM"]
    nat["PRCP_DEV_NAT"] = nat["PRCP_NAT"] - nat["PRCP_NAT_CLIM"]

    # ---- 宽表 ----
    wide = None
    for region in REGION_BOXES:
        sub = region_monthly[region_monthly.Region == region][
            ["Date", "T2M", "PRCP", "T2M_DEV", "PRCP_DEV"]
        ].rename(columns={
            "T2M": f"T2M_{region}", "PRCP": f"PRCP_{region}",
            "T2M_DEV": f"T2M_DEV_{region}", "PRCP_DEV": f"PRCP_DEV_{region}",
        })
        wide = sub if wide is None else wide.merge(sub, on="Date", how="outer")
    wide = wide.merge(
        nat[["Date", "T2M_NAT", "PRCP_NAT", "T2M_DEV_NAT", "PRCP_DEV_NAT"]],
        on="Date", how="outer",
    ).sort_values("Date").reset_index(drop=True)
    wide.to_csv(OUT_WIDE, index=False)
    print(f"[ok] 区域宽表 {len(wide)} 行 / {wide.Date.min()}~{wide.Date.max()} -> {OUT_WIDE.name}")

    # 概览
    print("\n[各区气候常态对比 (年均)]")
    for region in REGION_BOXES:
        s = region_monthly[region_monthly.Region == region]
        print(f"  {region:8s} T2M均={s.T2M.mean():.2f}°C  PRCP均={s.PRCP.mean():.1f}mm/月  格点={int(s.n_cells.iloc[0])}")


if __name__ == "__main__":
    build()
