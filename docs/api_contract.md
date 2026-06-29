# API 契约 (API Contract) v0.1

> **唯一事实源 (single source of truth)**：后端与前端的字段名以本文件为准。任何字段重命名或新增，需同一次提交里改双端 + 更新本文件。
>
> 适用范围：W2D1 ~ W2D5；W2D5 里程碑评审时由现场导师拍板定稿，进入 W3 后续阶段。

## 1. 端点总览

> URI 命名原则：用人能读懂的词（`check` / `palm-oil-price`），不用 `hello` / `series` 这类黑话。
> 旧路径 `/api/hello`、`/api/series` 仍保留为隐藏别名（`include_in_schema=False`），保证已写好的前端探针不返工。

| 方法 | 路径 | 旧别名 | 当前状态 | 用途 |
|---|---|---|---|---|
| GET | `/` | — | ✅ W2D1 已实现 | 赛博朋克数据中枢首页（中文说明 + 一键测试） |
| GET | `/check` | `/api/hello` | ✅ W2D1 已实现 | 检查后端是否在线 / 服务存活探针 |
| GET | `/palm-oil-price` | `/api/series` | ✅ W2D1 已实现 | 棕榈油历史价格 |
| GET | `/palm-3d-data` | — | ✅ 已实现 | 3D 演示数据（价格×时间×ONI 对齐） |
| GET | `/3d` | — | ✅ 已实现 | 后端自带赛博朋克 3D 演示页 |
| GET | `/docs` | — | ✅ W2D1 已实现 | 赛博朋克暗色主题接口文档 |
| GET | `/meteo` | — | 🟡 W2D5 计划 | 气象数据：ONI + 区域均值降水 |
| GET | `/predict` | — | 🟡 W2D5 计划 | 模型预测序列（含异常标注）|

## 2. 端点详情

### 2.1 GET /check （旧别名 /api/hello）

服务存活探针，前端在挂载时调用一次以确认后端可达。

**请求**：无参数。

**响应** (HTTP 200)：
```json
{
  "status": "ok",
  "service": "palm-oil-data-core",
  "version": "0.1.0",
  "message": "后端在线。试试 /palm-oil-price?symbol=palm"
}
```

### 2.2 GET /palm-oil-price （旧别名 /api/series）

返回棕榈油价格序列。

**请求参数**：

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `symbol` | string | 否 | `palm` | 品种代码，当前仅支持 `palm`（=棕榈油 CPO=F）|
| `start` | string | 否 | 无 | 起始日期 `YYYY-MM-DD`，inclusive |
| `end` | string | 否 | 无 | 终止日期 `YYYY-MM-DD`，inclusive |

**响应** (HTTP 200)：
```json
{
  "symbol": "palm",
  "source": "Yahoo Finance CPO=F (daily)",
  "freq": "daily",
  "rows": [
    {"date": "2024-01-02", "close": 795.75},
    {"date": "2024-01-03", "close": 789.25}
  ],
  "meta": {
    "rows": 2,
    "start": "2024-01-02",
    "end": "2024-01-03"
  }
}
```

说明：`meta.rows/start/end` 表示本次查询结果的条数和实际日期跨度，不是全量 CSV 的跨度。

**错误响应**：

| HTTP | 场景 | 示例 detail |
|---|---|---|
| 400 | start/end 日期格式不对 | `"bad date format: ..."` |
| 404 | 区间内 0 行 | `"no rows in requested range; check start/end"` |
| 500 | CSV 文件缺失 | `"Palm oil CSV not found: ..."` |

### 2.3 GET /palm-3d-data

给后端自带的 `/3d` 演示页用，把日频价格按「年-月」对齐到月度 Niño 3.4 ONI。

**请求参数**：同 `/palm-oil-price`（`symbol` / `start` / `end`）。

**响应** (HTTP 200)：
```json
{
  "symbol": "palm",
  "source": "Yahoo Finance CPO=F (daily) × NOAA Niño 3.4 ONI (monthly)",
  "rows": [
    {"date": "2024-01-02", "close": 795.75, "oni": -0.5}
  ],
  "meta": {"rows": 1, "start": "2024-01-02", "end": "2024-01-02"}
}
```

说明：`oni` 为该日所在月份的 ONI 值；若该月 ONI 尚未发布则为 `null`，前端按 0 兜底。

### 2.4 GET /meteo （W2D5 计划）

```json
{
  "rows": [
    {"date": "2006-01", "prcp": 13.87, "oni": -0.85, "station_count": 1}
  ]
}
```

### 2.4 GET /predict?n=N （W2D5 计划）

```json
{
  "model": "ensemble_v1",
  "trained_at": "2026-06-30T12:00:00Z",
  "rows": [
    {"date": "2026-07-01", "pred_close": 4123.5, "lower": 3980.1, "upper": 4250.0, "anomaly_flag": false}
  ]
}
```

## 3. 字段命名规则

1. 日期字段统一 `date` (小写)，格式 `YYYY-MM-DD`（日频）或 `YYYY-MM`（月频）。
2. 数值字段使用 snake_case，永远不用 camelCase（FastAPI/Pydantic 友好）。
3. 时间序列响应统一用 `rows: [...]` 而非 `data: [...]`，避免与 Axios/Fetch 的 `response.data` 混淆。
4. 元信息放在 `meta`，永远不与业务数据混在同一层。

## 4. CORS

- 开发期 (W2D1~)：仅允许 `http://localhost:5173` 与 `http://127.0.0.1:5173`
- 交付前：收紧为现场导师电脑实际地址，避免线上裸跑
