"""ECMWF 预测文件上传更新服务。

上传入口只接受 Copernicus/ECMWF 季节预测 NetCDF:
  - 必须包含 t2m (K) 和 tprate (m s**-1)
  - 必须包含 forecast_reference_time / forecastMonth / number / latitude / longitude
  - 解析成功后自动更新 processed/meteo CSV 与气候 Excel
  - 更新成功后清理预测缓存
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict

import pandas as pd
import xarray as xr

from app.core import predict_service

HERE = Path(__file__).resolve()
BACKEND_DIR = HERE.parents[2]
CODE_DIR = BACKEND_DIR.parent
PROJECT_ROOT = CODE_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_METEO_DIR = DATA_DIR / "raw" / "meteo"
PROCESSED_METEO_DIR = DATA_DIR / "processed" / "meteo"
SCRIPTS_DIR = CODE_DIR / "scripts"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import day13_pack_excel_archives as pack_archives  # noqa: E402
import day14_import_ecmwf_seasonal_forecast as ecmwf_import  # noqa: E402


class ForecastFileError(ValueError):
    """上传的文件不是本项目需要的 ECMWF 预测数据。"""


def _format_leads(leads: list[int]) -> str:
    if not leads:
        raise ForecastFileError("forecastMonth 为空。")
    if leads == list(range(min(leads), max(leads) + 1)):
        return f"lead{min(leads)}-{max(leads)}"
    return "lead" + "-".join(str(v) for v in leads)


def _inspect_netcdf(path: Path) -> Dict[str, object]:
    """只做内容识别，不落盘为正式数据。"""
    try:
        ds = xr.open_dataset(path, engine="h5netcdf")
    except Exception as exc:
        raise ForecastFileError(f"无法读取 NetCDF：{exc}") from exc

    required_vars = {"t2m", "tprate"}
    missing_vars = required_vars.difference(ds.data_vars)
    if missing_vars:
        raise ForecastFileError(f"缺少必要变量 {sorted(missing_vars)}，需要 t2m 和 tprate。")

    required_coords = {"forecast_reference_time", "forecastMonth", "number", "latitude", "longitude"}
    missing_coords = required_coords.difference(ds.coords)
    if missing_coords:
        raise ForecastFileError(f"缺少必要坐标 {sorted(missing_coords)}。")

    t2m_units = str(ds["t2m"].attrs.get("units", ""))
    tprate_units = str(ds["tprate"].attrs.get("units", ""))
    if t2m_units != "K":
        raise ForecastFileError(f"t2m 单位不是 K，当前为 {t2m_units!r}。")
    if tprate_units != "m s**-1":
        raise ForecastFileError(f"tprate 单位不是 m s**-1，当前为 {tprate_units!r}。")

    ref_times = pd.to_datetime(ds["forecast_reference_time"].values)
    leads = sorted(int(v) for v in ds["forecastMonth"].values)
    if len(ref_times) != 1:
        raise ForecastFileError(f"当前只支持单一起报时间，文件内有 {len(ref_times)} 个。")

    ref = pd.Timestamp(ref_times[0])
    target_months = [
        (ref.to_period("M").to_timestamp() + pd.DateOffset(months=lead - 1)).strftime("%Y-%m")
        for lead in leads
    ]
    return {
        "reference_date": ref.strftime("%Y-%m-%d"),
        "reference_ym": ref.strftime("%Y%m"),
        "leads": leads,
        "lead_label": _format_leads(leads),
        "target_months": target_months,
        "ensemble_members": int(len(ds["number"].values)),
        "lat_points": int(len(ds["latitude"].values)),
        "lon_points": int(len(ds["longitude"].values)),
        "lat_min": float(ds["latitude"].values.min()),
        "lat_max": float(ds["latitude"].values.max()),
        "lon_min": float(ds["longitude"].values.min()),
        "lon_max": float(ds["longitude"].values.max()),
    }


def _canonical_raw_path(meta: Dict[str, object]) -> Path:
    return (
        RAW_METEO_DIR
        / f"ecmwf_seasonal_forecast_malaysia_{meta['reference_ym']}_{meta['lead_label']}.nc"
    )


def update_forecast_from_bytes(filename: str, content: bytes) -> Dict[str, object]:
    """识别并导入上传的 ECMWF 文件，返回更新摘要。"""
    if not filename.lower().endswith(".nc"):
        raise ForecastFileError("非需要的文件：请上传 Copernicus/ECMWF 的 .nc NetCDF 文件。")
    if not content:
        raise ForecastFileError("上传文件为空。")

    RAW_METEO_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_METEO_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(suffix=".nc", delete=False) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        meta = _inspect_netcdf(tmp_path)
        raw_path = _canonical_raw_path(meta)
        shutil.copyfile(tmp_path, raw_path)

        grid = ecmwf_import.build_grid_table(raw_path)
        if grid.empty:
            raise ForecastFileError("NetCDF 可读取，但解析后网格表为空。")
        regional_mean = ecmwf_import.build_regional_mean(grid)

        grid.to_csv(ecmwf_import.OUT_GRID, index=False)
        regional_mean.to_csv(ecmwf_import.OUT_MEAN, index=False)

        climate_xlsx, climate_meta = pack_archives.build_climate_workbook()
        predict_service.clear_cache()

        return {
            "status": "updated",
            "message": "ECMWF 预测文件已识别并完成更新。",
            "raw_file": str(raw_path.relative_to(PROJECT_ROOT)),
            "grid_csv": str(ecmwf_import.OUT_GRID.relative_to(PROJECT_ROOT)),
            "regional_mean_csv": str(ecmwf_import.OUT_MEAN.relative_to(PROJECT_ROOT)),
            "climate_excel": str(climate_xlsx.relative_to(PROJECT_ROOT)),
            "target_months": sorted(grid["TARGET_YM"].astype(str).unique().tolist()),
            "rows_grid": int(len(grid)),
            "rows_regional_mean": int(len(regional_mean)),
            "climate_excel_rows": int(climate_meta["ecmwf_forecast_rows"]),
            "reference_date": meta["reference_date"],
            "lead_months": meta["leads"],
            "ensemble_members": meta["ensemble_members"],
            "grid_points_per_member": int(meta["lat_points"]) * int(meta["lon_points"]),
            "bounds": {
                "north": meta["lat_max"],
                "south": meta["lat_min"],
                "west": meta["lon_min"],
                "east": meta["lon_max"],
            },
        }
    finally:
        try:
            os.unlink(tmp_path)
        except FileNotFoundError:
            pass
