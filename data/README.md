# Data Directory · 数据目录

> El Niño × 亚太农产品期货项目 — 全部原始 / 处理后 / 可视化数据集中目录。
> 数据按用途分三层：`raw/`（不动）、`processed/`（脚本可重生成）、`figures/`（出图）。

## 目录结构

```
data/
├── raw/                                  # 原始未处理数据（don't touch）
│   ├── meteo/                            # 气象类原始数据
│   │   ├── malaysia_prcp.csv             马来西亚 2 站月度降水 (NOAA NCEI · GHCN)
│   │   ├── 马来西亚平均温度.csv              马来西亚 Kota Kinabalu 日频温度 (NOAA daily)
│   │   ├── nasa_power_malaysia_prcp_monthly_2007_2025.csv
│   │   │                                   NASA POWER 区域月度降水 (PRECTOTCORR_SUM, mm/month)
│   │   ├── nasa_power_malaysia_t2m_monthly_2007_2025.csv
│   │   │                                   NASA POWER 区域月均温 (T2M, °C)
│   │   ├── noaa_nino34_pacific_oni_raw.txt
│   │   │                                   NOAA CPC oni.ascii.txt (1950–至今)
│   │   ├── ecmwf_seasonal_forecast_malaysia_202606_lead1-6.nc
│   │   │                                   Copernicus/ECMWF 马来西亚季节预测 NetCDF (2026-06 起报, leadtime=1–6)
│   │   └── legacy_noaa_nino34_pacific_oni.xlsx
│   │                                       旧版 17 年 ONI（留档）
│   └── product/                          # 产品/品种类原始数据
│       ├── CPO_F_daily_yahoo.csv         棕榈油期货日线 (Yahoo Finance · CPO=F)
│       ├── ifind_edb_palm_oil_production_my.csv
│                                           马来西亚毛棕榈油月度产量原始表 (iFinD EDB · S002958800)
│       └── ifind_edb_palm_oil_production_id.csv
│                                           印度尼西亚毛棕榈油月度产量原始表 (iFinD EDB · S019729740)
│
├── processed/                            # 脚本生成的派生数据（可重新构建）
│   ├── meteo/                            # 气象类派生数据
│   │   ├── noaa_nino34_pacific_oni_wide.csv
│   │   ├── noaa_nino34_pacific_oni_monthly.csv
│   │   ├── malaysia_prcp_regional.csv
│   │   ├── malaysia_temperature_monthly.csv
│   │   ├── nasa_power_malaysia_weather_monthly.csv
│   │   ├── ecmwf_seasonal_forecast_malaysia_grid.csv
│   │   ├── ecmwf_seasonal_forecast_malaysia_regional_mean.csv
│   │   └── kuala_lumpur_malaysia_prcp_noaa_nino34_pacific_oni_merged.csv
│   └── product/                          # 产品/品种类派生数据
│       ├── CPO_F_calendar_gaps.csv
│       ├── palm_oil_production_my_monthly.csv
│       ├── palm_oil_production_id_monthly.csv
│       └── palm_oil_production_my_weekly_estimated.csv
│                                           周度估算产量报告，单位：吨
│
└── figures/                              # 输出图表（供报告引用）
    ├── prcp_trend.png                    降水 19 年走势图（含 max/min 标注）
    └── CPO_F_price_trend.png             棕榈油 12 年价格走势图（标注 2015-2016 大缺口）
```

## 一键复现流程

所有脚本都用 `__file__` 推算项目根，在任何工作目录下均可运行：

```bash
cd "ONI project"

# Day 4 — 气象数据流
python3 code/scripts/day4_explore_prcp.py       # 1. 探查降水原始数据
python3 code/scripts/day4_plot_prcp.py          # 2. 绘制降水折线图
python3 code/scripts/day4_build_oni_wide.py     # 3. NOAA ascii → ONI 宽表
python3 code/scripts/day4_reshape_oni.py        # 4. pandas.melt() 宽 → 长
python3 code/scripts/day4_merge_prcp_oni.py     # 5. 区域平均 + 与 ONI 合并
python3 code/scripts/day9_build_malaysia_temperature_monthly.py # 6. 日频温度 → 月度温度特征
python3 code/scripts/day10_build_nasa_power_malaysia_weather.py # 7. NASA POWER 区域降水/温度 → 月度天气表
python3 code/scripts/day14_import_ecmwf_seasonal_forecast.py # 8. ECMWF NetCDF 季节预测 → 网格长表 + 区域均值

# Day 5 — 棕榈油价格流
python3 code/scripts/day5_download_palm_oil_yahoo.py    # 1. 拉取 Yahoo CPO=F
python3 code/scripts/day5_explore_plot_palm_oil.py      # 2. 缺口检测 + 走势图
python3 code/scripts/day5_build_palm_oil_day5_report.py # 3. 生成 Day5 报告（输出到 reports/）

# Day 8 — iFinD EDB 产量数据流
python3 code/scripts/day8_fetch_ifind_edb.py \
  --indicators S002958800 \
  --start 2007-01-01 --end 2026-06-22 \
  --slug palm_oil_production_my

python3 code/scripts/day8_fetch_ifind_edb.py \
  --indicators S019729740 \
  --start 2007-01-01 --end 2026-06-23 \
  --slug palm_oil_production_id

python3 code/scripts/day8_build_palm_oil_production_weekly.py # 原始月度产量 → 月度清洗表 + 周度估算表
```

依赖：`pandas`、`matplotlib`、`openpyxl`（读旧 xlsx）、`yfinance`、`python-docx`、`xarray`、`h5netcdf`、`h5py`。
其中 iFinD EDB 脚本需要 `~/.cache/ifind/tokens.json` 中存在有效 `refresh_token`。

## 关键数据集

| 文件 | 行 × 列 | 时间跨度 | 缺失 | 备注 |
|---|---|---|---|---|
| `raw/meteo/malaysia_prcp.csv` | 341 × 7 | 2006-01 ~ 2025-05 | 0 | 2 个 GHCN 站点 |
| `raw/meteo/马来西亚平均温度.csv` | 25804 × 7 | 1955-01-01 ~ 2025-08-24 | TAVG 11.18% | NOAA 日频站点温度，华氏度 |
| `raw/meteo/nasa_power_malaysia_prcp_monthly_2007_2025.csv` | 3600 × 17 | 2007-01 ~ 2025-12 | 0 | NASA POWER 区域网格降水，PRECTOTCORR_SUM，单位 mm/month |
| `raw/meteo/nasa_power_malaysia_t2m_monthly_2007_2025.csv` | 3600 × 17 | 2007-01 ~ 2025-12 | 0 | NASA POWER 区域网格月均温，T2M，单位 °C |
| `raw/meteo/ecmwf_seasonal_forecast_malaysia_202606_lead1-6.nc` | 51 集合成员 × 168 网格点 × 6 目标月 | 起报 2026-06，目标 2026-06 ~ 2026-11 | 0 | Copernicus/ECMWF 季节预测，含 2m 气温与总降水率 |
| `raw/product/CPO_F_daily_yahoo.csv` | 2986 × 7 | 2014-01-02 ~ 2026-06-18 | 0 | Yahoo Finance 日线 |
| `raw/product/ifind_edb_palm_oil_production_my.csv` | 233 × 5 | 2007-01-31 ~ 2026-05-31 | 0 | iFinD EDB 原始长表 |
| `raw/product/ifind_edb_palm_oil_production_id.csv` | 74 × 5 | 2020-01-31 ~ 2026-03-31 | 缺 2022-11 | iFinD EDB 原始长表 |
| `processed/meteo/noaa_nino34_pacific_oni_wide.csv` | 77 × 13 | 1950 – 2026 | 末年部分季节空 | NOAA CPC ONI v5 |
| `processed/meteo/noaa_nino34_pacific_oni_monthly.csv` | 916 × 2 | 1950-01 ~ 2026-04 | 0 | 月度长表 |
| `processed/meteo/malaysia_prcp_regional.csv` | 209 × 3 | 2006-01 ~ 2025-05 | 0 | 站点均值 |
| `processed/meteo/kuala_lumpur_malaysia_prcp_noaa_nino34_pacific_oni_merged.csv` | 209 × 4 | 2006-01 ~ 2025-05 | 0 | PRCP + ONI 早期合并表 |
| `processed/meteo/malaysia_temperature_monthly.csv` | 848 × 11 | 1955-01 ~ 2025-08 | 2007 后 TAVG 无缺失 | 日频 TAVG 聚合月均温，含摄氏度与同月距平 |
| `processed/meteo/nasa_power_malaysia_weather_monthly.csv` | 228 × 14 | 2007-01 ~ 2025-12 | 0 | NASA POWER 区域平均 PRCP + TAVG_C + TAVG_C_ANOMALY；气候 Excel 中拆为唯一降水表和唯一气温表 |
| `processed/meteo/ecmwf_seasonal_forecast_malaysia_grid.csv` | 51408 × 13 | 起报 2026-06，目标 2026-06 ~ 2026-11 | 0 | ECMWF 季节预测网格长表，含 `T2M_C` 与 `PRCP_MM_PER_MONTH` 单位换算；气候 Excel 预测 Sheet 使用此表 |
| `processed/meteo/ecmwf_seasonal_forecast_malaysia_regional_mean.csv` | 6 × 11 | 2026-06 ~ 2026-11 | 0 | ECMWF 51 集合成员 × 168 网格点区域均值，留作快速核对，不作为气候 Excel 主表 |
| `processed/product/CPO_F_calendar_gaps.csv` | 视检测 | 2014–2026 | 0 | ≥3 日缺口列表 |
| `processed/product/palm_oil_production_my_monthly.csv` | 233 × 5 | 2007-01-31 ~ 2026-05-31 | 0 | 毛棕榈油产量月度清洗表，单位：吨 |
| `processed/product/palm_oil_production_id_monthly.csv` | 74 × 5 | 2020-01-31 ~ 2026-03-31 | 缺 2022-11 | 印度尼西亚毛棕榈油产量月度清洗表 |
| `processed/product/palm_oil_production_my_weekly_estimated.csv` | 1013 × 11 | 2007-01-01 ~ 2026-05-31 | 0 | 周度估算产量报告，单位：吨 |

## 数据来源

- **ONI**：NOAA CPC 官方 [`oni.ascii.txt`](https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt)，代表 Niño 3.4 太平洋海区，不是单一气象站点
- **降水**：NOAA NCEI GHCN 月度数据，吉隆坡两站（KLIA `MYM00048650` + Sultan Abdul Aziz Shah `MYM00048647`）
- **温度**：NOAA NCEI 日频站点数据（Kota Kinabalu International `MYM00096471`）。`TMAX/TMIN` 原始缺失率高，暂不作为主分析字段。
- **NASA POWER 区域天气表**：NASA POWER 区域月度数据（约 `1.0–6.5°N`, `100.0–109.375°E`），`PRECTOTCORR_SUM` 作为月累计降水 `PRCP`，`T2M` 作为月均温 `TAVG_C`。该数据覆盖到 `2025-12`，可作为后续重新设计模型时的候选气象源。
- **ECMWF/Copernicus 季节预测**：Climate Data Store · `Seasonal forecast monthly statistics on single levels`，本次文件为 ECMWF system 51，区域约 `0.5–7.5°N`, `99.5–119.5°E`，2026-06 起报、`leadtime_month=1–6`，按 CDS 口径对应目标月 `2026-06` ~ `2026-11`。原变量 `t2m` 单位 K，`tprate` 单位 m/s，解析脚本仅做单位换算（K→°C，m/s→mm/month）。
- **棕榈油价格**：Yahoo Finance · `CPO=F`（Crude Palm Oil Futures, Bursa Malaysia Derivatives）
- **棕榈油产量（马来西亚）**：同花顺 iFinD EDB · `S002958800`（`产量:毛棕榈油:马来西亚`），数据源为马来西亚棕榈油局（MPOB）
- **棕榈油产量（印度尼西亚）**：同花顺 iFinD EDB · `S019729740`（`棕榈油:毛棕榈油:产量:印度尼西亚`）

## Excel 气候归档口径

`processed/archives/02_climate_data_malaysia.xlsx` 按“每种数据只保留一份”重新整理，只保留 4 张数据表：

- `01_MY_PRCP_History`：马来西亚过去降水，来自 `processed/meteo/nasa_power_malaysia_weather_monthly.csv` 的 `PRCP` 主口径。
- `02_MY_TAVG_History`：马来西亚过去气温，来自 `processed/meteo/nasa_power_malaysia_weather_monthly.csv` 的 `TAVG_C` 主口径。
- `03_ONI_Monthly`：ONI 月度数据，来自 `processed/meteo/noaa_nino34_pacific_oni_monthly.csv`。
- `04_MY_Climate_Forecast`：马来西亚气候预测，来自 `processed/meteo/ecmwf_seasonal_forecast_malaysia_grid.csv`。

已从气候 Excel 中移除重复口径：NOAA 降水站点、NOAA 日频温度站点、ONI ASCII 原始表、NASA POWER 原始网格宽表。原始文件仍保留在 `raw/` 或 `processed/`，只是 Excel 归档不再重复收录。

后续模型搭建默认以三本 Excel 为正式输入：

- `processed/archives/01_palm_oil_planted_area_malaysia.xlsx`
- `processed/archives/02_climate_data_malaysia.xlsx`
- `processed/archives/03_palm_oil_production_malaysia.xlsx`

## 周度估算产量说明

`S002958800` 原始频率是月度，因此 `processed/product/palm_oil_production_my_weekly_estimated.csv` 是估算表，不是真实周度观测。估算方法：先将每个月的 `CPO_PRODUCTION_TONNES` 按该月自然日数平均分摊为每日估计值，再按 Monday-Sunday 自然周加总为 `CPO_PRODUCTION_TONNES_WEEKLY_EST`。这个方法的好处是可以和周度/日度价格数据对齐，并且所有周度估算值加总后仍严格等于原始月度总量。

## 贴合度验证

- **ONI 贴合项目目标**：ONI 是 El Niño / La Niña 的标准气候冲击指标，直接刻画太平洋海温异常。对“气候变化/ENSO → 马来西亚棕榈油供给 → 价格”的传导链有解释意义。当前数据与棕榈油月均收盘价在 0-3 个月滞后下相关性约为 `-0.45` 到 `-0.47`，说明它可以作为后续特征工程中的气候因子，但不能单独作为因果结论。
- **降水站点为留档数据**：NOAA 吉隆坡两个机场站点保留用于早期报告和对照；NASA POWER 的 `PRECTOTCORR_SUM` 是月累计毫米口径，可作为后续模型重建时的区域降水候选源。
- **温度数据说明**：NASA POWER 区域 `T2M` 与 NOAA 日频站点温度均已保留。旧预测模块已移除，后续是否使用温度距平作为胁迫变量，需要按新的计算方法重新定义。
