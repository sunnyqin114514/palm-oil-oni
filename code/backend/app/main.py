"""FastAPI 主入口 (entry point)。

第一周交付物 6 (R4) 的最小后端 + 赛博朋克风格的易懂界面。

界面 / 端点一览：
  - GET /                赛博朋克数据中枢首页（中文说明 + 一键测试按钮）
  - GET /check           检查后端是否在线（旧别名 /api/hello）
  - GET /palm-oil-price  取棕榈油历史价格（旧别名 /api/series）
  - GET /docs            赛博朋克暗色主题的开发者接口文档

URI 命名原则：用「人能读懂的词」(check / palm-oil-price)，不用 hello/series 这类程序员黑话。
旧的 /api/hello、/api/series 仍保留为隐藏别名，保证已写好的前端探针不返工。
"""

from __future__ import annotations

import os
from typing import List, Literal, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.core import data as data_loader
from app.core import forecast_update
from app.core import llm as llm_service
from app.core import predict_service

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(HERE, "static")
NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

app = FastAPI(
    title="棕榈油数据中枢 · Palm Oil Data Core",
    description="Sunny 期货实习项目 — 棕榈油 × 厄尔尼诺。读取数据并以统一接口输出给网页与后续分析模块。",
    version="0.1.0",
    docs_url=None,       # 关掉默认 docs，下面换成赛博朋克主题版
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
    allow_credentials=False,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── 响应模型 (response models) ────────────────────────────────────────────────

class CheckResponse(BaseModel):
    status: str
    service: str
    version: str
    message: str


class PriceRow(BaseModel):
    date: str
    close: float


class PriceResponse(BaseModel):
    symbol: str
    source: str
    freq: str
    rows: List[PriceRow]
    meta: dict


class Point3DRow(BaseModel):
    date: str
    close: float
    oni: Optional[float] = None


class Scene3DResponse(BaseModel):
    symbol: str
    source: str
    rows: List[Point3DRow]
    meta: dict


class PredictionContributions(BaseModel):
    intercept: float
    trend: float
    ONI: float
    PRCP: float
    TAVG: float
    INTX_West: float = 0.0
    seasonality: float


class ProductionPrediction(BaseModel):
    target_month: str
    predicted_yield: float
    predicted_production_tonnes: float
    mature_area_hectares: float
    mature_area_year: int
    weather_source: str
    accuracy: dict
    inputs: dict
    contributions: PredictionContributions
    model: dict


class PredictionRangeResponse(BaseModel):
    source: str
    rows: List[ProductionPrediction]
    meta: dict


class PredictionExplainResponse(BaseModel):
    prediction: ProductionPrediction
    explanation: str
    llm_source: str
    note: str


class ForecastUpdateResponse(BaseModel):
    status: str
    message: str
    raw_file: str
    grid_csv: str
    regional_mean_csv: str
    climate_excel: str
    target_months: List[str]
    rows_grid: int
    rows_regional_mean: int
    climate_excel_rows: int
    reference_date: str
    lead_months: List[int]
    ensemble_members: int
    grid_points_per_member: int
    bounds: dict


# ── 页面：首页 + 自定义赛博朋克 docs ───────────────────────────────────────────

@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    """赛博朋克数据中枢首页。"""
    return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers=NO_CACHE_HEADERS)


@app.get("/docs", include_in_schema=False)
def cyberpunk_docs():
    """赛博朋克暗色主题的 Swagger 文档。"""
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="棕榈油数据中枢 · 接口文档",
        swagger_css_url="/static/cyberpunk-docs.css",
    )


@app.get("/3d", include_in_schema=False)
def scene_3d() -> FileResponse:
    """后端自带的赛博朋克 3D 预测页（时间 × 天气影响 × 预测产量）。"""
    return FileResponse(os.path.join(STATIC_DIR, "scene3d.html"), headers=NO_CACHE_HEADERS)


# ── 业务端点 ──────────────────────────────────────────────────────────────────

def _build_check() -> CheckResponse:
    return CheckResponse(
        status="ok",
        service="palm-oil-data-core",
        version="0.1.0",
        message="后端在线。试试 /palm-oil-price?symbol=palm",
    )


def _query_meta(rows: list[dict]) -> dict:
    """返回本次查询区间的元信息，避免前端误读为全量数据跨度。"""
    return {
        "rows": len(rows),
        "start": rows[0]["date"],
        "end": rows[-1]["date"],
    }


def _build_price(
    symbol: str,
    start: Optional[str],
    end: Optional[str],
) -> PriceResponse:
    try:
        rows = data_loader.palm_rows(start=start, end=end)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"日期格式不对 (应为 YYYY-MM-DD): {exc}")

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="该区间内没有数据，请检查 start / end",
        )

    return PriceResponse(
        symbol=symbol,
        source="Yahoo Finance CPO=F (daily)",
        freq="daily",
        rows=rows,
        meta=_query_meta(rows),
    )


@app.get("/check", response_model=CheckResponse, summary="检查后端是否在线", tags=["数据中枢"])
def check() -> CheckResponse:
    """点一下确认服务存活；前端挂载时也会调用它做探针。"""
    return _build_check()


@app.get(
    "/palm-oil-price",
    response_model=PriceResponse,
    summary="取棕榈油历史价格",
    tags=["数据中枢"],
)
def palm_oil_price(
    symbol: Literal["palm"] = Query("palm", description="品种，目前仅支持 palm（棕榈油）"),
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD（含当天，可不填）"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD（含当天，可不填）"),
) -> PriceResponse:
    """返回棕榈油每日收盘价。不填日期=取全部；填区间=只取该段。"""
    return _build_price(symbol, start, end)


@app.get(
    "/palm-3d-data",
    response_model=Scene3DResponse,
    summary="取 3D 演示数据（价格×时间×ONI）",
    tags=["数据中枢"],
)
def palm_3d_data(
    symbol: Literal["palm"] = Query("palm", description="品种，目前仅支持 palm（棕榈油）"),
    start: Optional[str] = Query(None, description="开始日期 YYYY-MM-DD（含当天，可不填）"),
    end: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD（含当天，可不填）"),
) -> Scene3DResponse:
    """给 /3d 页面用：每条数据含日期、收盘价、以及该月对齐的 Niño 3.4 ONI 值。"""
    try:
        rows = data_loader.palm_with_oni(start=start, end=end)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"日期格式不对 (应为 YYYY-MM-DD): {exc}")

    if not rows:
        raise HTTPException(status_code=404, detail="该区间内没有数据，请检查 start / end")

    return Scene3DResponse(
        symbol=symbol,
        source="Yahoo Finance CPO=F (daily) × NOAA Niño 3.4 ONI (monthly)",
        rows=[Point3DRow(**r) for r in rows],
        meta=_query_meta(rows),
    )


# ── 产量预测端点（后端线性模型实算）──────────────────────────────────────────

@app.get(
    "/predict-production",
    response_model=ProductionPrediction,
    summary="预测某月棕榈油产量（线性模型实算）",
    tags=["产量预测"],
)
def predict_production(
    target_month: str = Query(
        ...,
        description="目标月份 YYYY-MM，例如 2026-11；也支持 2026-7 并自动补零",
        pattern=r"^\d{4}-\d{1,2}$",
    ),
) -> ProductionPrediction:
    """用最新三维模型实算目标月单产与绝对产量，返回逐因子贡献与天气来源。"""
    try:
        result = predict_service.predict_one(target_month)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"模型权重缺失：{exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"目标月份格式不对（应为 YYYY-MM）：{exc}")
    return ProductionPrediction(**result)


@app.get(
    "/predict-production-range",
    response_model=PredictionRangeResponse,
    summary="连续预测多个月棕榈油产量",
    tags=["产量预测"],
)
def predict_production_range(
    start_month: str = Query(
        ...,
        description="起始月份 YYYY-MM，例如 2026-06；也支持 2026-7 并自动补零",
        pattern=r"^\d{4}-\d{1,2}$",
    ),
    months: int = Query(12, ge=1, le=24, description="连续预测的月数（1~24）"),
) -> PredictionRangeResponse:
    """给网站做未来多月预测：从 start_month 起连续算 months 个月。"""
    try:
        rows = predict_service.predict_many(start_month, months)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"模型权重缺失：{exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"参数不对：{exc}")

    return PredictionRangeResponse(
            source="Malaysia palm oil 3D OLS yield model (Trend + ONI + precipitation + temperature + West T×P interaction + seasonality)",
        rows=[ProductionPrediction(**r) for r in rows],
        meta={
            "rows": len(rows),
            "start": rows[0]["target_month"],
            "end": rows[-1]["target_month"],
        },
    )


@app.get(
    "/predict-explain",
    response_model=PredictionExplainResponse,
    summary="预测某月产量并用 DeepSeek 解读",
    tags=["产量预测"],
)
def predict_explain(
    target_month: str = Query(
        ...,
        description="目标月份 YYYY-MM，例如 2026-11；也支持 2026-7 并自动补零",
        pattern=r"^\d{4}-\d{1,2}$",
    ),
) -> PredictionExplainResponse:
    """先用线性模型实算，再把结果交给 DeepSeek 生成中文解读（无 Key 自动本地降级）。"""
    try:
        result = predict_service.predict_one(target_month)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"模型权重缺失：{exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"目标月份格式不对（应为 YYYY-MM）：{exc}")

    explained = llm_service.explain_prediction(result)
    return PredictionExplainResponse(
        prediction=ProductionPrediction(**result),
        explanation=explained["explanation"],
        llm_source=explained["llm_source"],
        note=explained.get("note", ""),
    )


@app.post(
    "/update-climate-forecast",
    response_model=ForecastUpdateResponse,
    summary="上传 ECMWF NetCDF 并自动更新气候预测",
    tags=["产量预测"],
)
async def update_climate_forecast(
    file: UploadFile = File(..., description="Copernicus/ECMWF .nc 文件"),
) -> ForecastUpdateResponse:
    """识别上传的 NetCDF；若不是所需 ECMWF 预测数据，返回明确错误。"""
    try:
        content = await file.read()
        result = forecast_update.update_forecast_from_bytes(file.filename or "", content)
    except forecast_update.ForecastFileError as exc:
        detail = str(exc)
        if not detail.startswith("非需要的文件"):
            detail = f"非需要的文件：{detail}"
        raise HTTPException(status_code=400, detail=detail)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=f"更新依赖文件缺失：{exc}")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"文件内容不符合要求：{exc}")
    return ForecastUpdateResponse(**result)


# ── 旧别名：保持前端 / 旧文档不返工（不在 docs 中显示）─────────────────────────

@app.get("/api/hello", response_model=CheckResponse, include_in_schema=False)
def hello_alias() -> CheckResponse:
    return _build_check()


@app.get("/api/series", response_model=PriceResponse, include_in_schema=False)
def series_alias(
    symbol: Literal["palm"] = Query("palm"),
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
) -> PriceResponse:
    return _build_price(symbol, start, end)
