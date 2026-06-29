# -*- coding: utf-8 -*-
"""把温度研究 + 三维模型结果作为新 sheet 追加到研究总表 (保留原有 sheet)。

新增:
  08_Regional_Weather   三区月度气温/降水(宽表)
  09_Temp_WindowSearch  维度a 积温窗口搜索
  10_Temp_Asymmetry     维度b 高温/低温非对称
  11_Temp_SpatialIntx   维度c 温度×降水空间交互
  12_Model3D_Validation 三维模型 × 变体 样本外指标
  13_Model3D_Weights    推荐模型权重(键值)
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
MASTER = PROJECT_ROOT / "data" / "processed" / "archives" / "00_palm_oil_research_master_malaysia.xlsx"
MODEL_DIR = PROJECT_ROOT / "code" / "model"
TEMP_DIR = MODEL_DIR / "temp_research"
METEO_DIR = PROJECT_ROOT / "data" / "processed" / "meteo"


def main() -> None:
    reg = pd.read_csv(METEO_DIR / "malaysia_regional_weather_wide.csv")
    dim_a = pd.read_csv(TEMP_DIR / "dim_a_window.csv")
    dim_b = pd.read_csv(TEMP_DIR / "dim_b_asymmetry.csv")
    dim_c = pd.read_csv(TEMP_DIR / "dim_c_spatial.csv")
    metrics = pd.read_csv(MODEL_DIR / "model3d_validation_metrics.csv")
    w = json.loads((MODEL_DIR / "model3d_weights.json").read_text(encoding="utf-8"))

    wrows = [["model_name", w["model_name"]], ["variant", w["variant"]],
             ["trained_window", w["trained_window"]], ["test_window", w["test_window"]],
             ["intercept", w["intercept"]]]
    for k, v in w["coef"].items():
        wrows.append([f"coef[{k}]", v])
    for k, v in w["p_values"].items():
        wrows.append([f"p[{k}]", v])
    for k, v in w["metrics"].items():
        wrows.append([f"metric[{k}]", v])
    wdf = pd.DataFrame(wrows, columns=["key", "value"])

    sheets = {
        "08_Regional_Weather": reg,
        "09_Temp_WindowSearch": dim_a,
        "10_Temp_Asymmetry": dim_b,
        "11_Temp_SpatialIntx": dim_c,
        "12_Model3D_Validation": metrics,
        "13_Model3D_Weights": wdf,
    }
    with pd.ExcelWriter(MASTER, engine="openpyxl", mode="a",
                        if_sheet_exists="replace") as xw:
        for name, df in sheets.items():
            df.to_excel(xw, sheet_name=name, index=False)
            print(f"  + {name}: {df.shape[0]}行 x {df.shape[1]}列")
    print(f"[ok] 已追加 6 个 sheet -> {MASTER.name}")


if __name__ == "__main__":
    main()
