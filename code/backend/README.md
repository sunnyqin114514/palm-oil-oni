# Backend — Palm Oil API

FastAPI 最小后端，对应**第一周交付物 6 (R4 / Day 6)**。

## 目录结构（位于 `code/backend/`）

```
code/backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI 入口，含 /api/hello、/api/series
│   └── core/
│       ├── __init__.py
│       └── data.py      # 数据载入层 (palm CSV / ONI / 降水 / 合并表)
├── requirements.txt
├── README.md
└── .venv/               # 本地虚拟环境（gitignored）
```

## 一键启动

```bash
cd "ONI project/code/backend"

# 第一次：建 venv 并装包
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 启动服务
uvicorn app.main:app --reload --port 8000
```

打开浏览器：
- http://127.0.0.1:8000/api/hello → 服务存活
- http://127.0.0.1:8000/api/series?symbol=palm → 棕榈油全量价格 JSON（2986 行）
- http://127.0.0.1:8000/api/series?symbol=palm&start=2024-01-01&end=2024-03-31 → 按日期切片
- http://127.0.0.1:8000/docs → FastAPI 自动生成的 Swagger UI，可点按钮直接调用

## 端点契约

字段、错误码以根目录 `docs/api_contract.md` 为唯一事实源。

## 数据源

由 `app/core/data.py` 通过 `os.path.dirname(__file__)` 推算项目根，所有数据路径**统一指向顶层 `data/`**：

| 常量 | 路径（相对项目根） | 当前用途 |
|---|---|---|
| `PALM_CSV` | `data/raw/product/CPO_F_daily_yahoo.csv` | `/api/series` |
| `ONI_LONG_CSV` | `data/processed/meteo/noaa_nino34_pacific_oni_monthly.csv` | notebook、W2D2 起特征工程 |
| `PRCP_ONI_CSV` | `data/processed/meteo/kuala_lumpur_malaysia_prcp_noaa_nino34_pacific_oni_merged.csv` | notebook、W2D2 起特征工程 |
| `PRCP_REGIONAL_CSV` | `data/processed/meteo/malaysia_prcp_regional.csv` | notebook 备查 |
| `PALM_PRODUCTION_CSV` | `data/processed/product/palm_oil_production_my_weekly_estimated.csv` | 周度估算产量特征 |

数据流的生成脚本见 `code/scripts/day4_*.py` 与 `code/scripts/day5_*.py`，复现命令见 `data/README.md`。

## 产量预测端点（W3 新增）

线性模型实算在 `code/model/`，后端通过 `app/core/predict_service.py` 调用，DeepSeek 解读在 `app/core/llm.py`。

| 端点 | 说明 |
|---|---|
| `GET /predict-production?target_month=2026-11` | 单月预测：单产、总产量吨数、逐因子贡献、天气来源 |
| `GET /predict-production-range?start_month=2026-06&months=12` | 连续多月预测 |
| `GET /predict-explain?target_month=2026-11` | 先实算再用 DeepSeek 生成中文解读（无 Key 自动本地降级） |
| `POST /update-climate-forecast` | 上传 Copernicus/ECMWF `.nc` 文件，自动识别、解析并更新气候 Excel 与预测缓存 |

分工：**后端线性模型算数，DeepSeek 只解读，不产生预测数字。** 天气优先用气候 Excel 的
`04_MY_Climate_Forecast`（ECMWF），缺失月份回退历史同期常态，返回 `weather_source` 透明标注。

### DeepSeek 配置（可选）

```bash
cd "ONI project/code/backend"
cp .env.example .env
# 编辑 .env 填入 DEEPSEEK_API_KEY
```

不配置 Key 时 `/predict-explain` 自动使用本地规则解读，网站照常可用。

### 更新 ECMWF 预测文件

首页有“更新气候预测文件”卡片，含 Copernicus 下载页面直达链接。下载新的
`Seasonal forecast monthly statistics on single levels` NetCDF 后，直接拖入网页上传区即可。

后端会检查文件内容，必须包含 `t2m`、`tprate`、`forecastMonth`、`latitude`、`longitude`
等 ECMWF 季节预测字段。若上传的不是所需预测文件，会返回“非需要的文件”。

上传成功后自动完成：

- 保存原始 `.nc` 到 `data/raw/meteo/`
- 重新生成 ECMWF grid / regional mean CSV
- 更新 `02_climate_data_malaysia.xlsx` 的 `04_MY_Climate_Forecast`
- 清理预测缓存，让网站立即使用新的高精度预测区间

## CORS

开发期允许 `http://localhost:5173` 与 `http://127.0.0.1:5173`（Vite 默认端口）。
要从其他端口/域名访问，编辑 `app/main.py` 里的 `allow_origins`。

## W2D 后续扩展

- W2D3：补 `prophet` 依赖（若 pip 装失败转 conda 或改 SARIMAX）
- W2D4：补 `xgboost`
- W2D5：拆 `app/routers/`，加 `/api/meteo` 与 `/api/predict?n=N`
