# Sunny 期货实习 — 棕榈油 × 厄尔尼诺 项目

> 单品种聚焦：Palm Oil (`CPO=F`)。后端 FastAPI + 前端 react-three-fiber 3D 可视化 + 预测模型。

## 目录结构（W2D1 收工 · 按"性质"分类）

```
ONI project/
├── README.md                       # 项目总说明（本文件）
├── .gitignore
│
├── reports/                        # 学习报告 · 阶段日报 · 项目规划
│   ├── Day2_Learning_Report.docx
│   ├── Day3-4_Learning_Report.docx
│   ├── Day4_Learning_Report.docx           气象数据采集 (PRCP + ONI)
│   ├── Day5_Learning_Report.docx           棕榈油价格采集 + IMF 阅读
│   └── plans/                              项目规划与作战文档
│       ├── sunny实习三周(1).pdf
│       └── Sunny_期货实习全量作战文档_..._新版.pdf
│
├── code/                           # 编程模型 · 三段子目录平行
│   ├── backend/                            FastAPI 后端 (R4 / Day 6 交付)
│   │   ├── app/main.py                       端点 /api/hello、/api/series
│   │   ├── app/core/data.py                  数据载入层（与 notebook 共用）
│   │   ├── requirements.txt
│   │   └── README.md
│   ├── frontend/                           React + r3f 3D 原型 (R5 / Day 7 交付)
│   │   ├── src/                              TS 源码（Scene3D.tsx 等）
│   │   ├── package.json
│   │   └── README.md
│   ├── notebooks/
│   │   └── 01_palm_oil_eda.ipynb           棕榈油 + ONI + 降水 描述性统计与走势
│   └── scripts/                            8 个一次性数据流脚本（按日期前缀）
│       ├── day4_*.py                         气象数据 5 步走 (探查/绘图/宽表/melt/合并)
│       └── day5_*.py                         棕榈油价格 3 步走 (下载/缺口/构建报告)
│
├── data/                           # 全部数据集中（详见 data/README.md）
│   ├── raw/                                原始未处理数据（meteo / product）
│   ├── processed/                          派生数据（meteo / product，可重建）
│   ├── figures/                            出图（供报告引用）
│   └── README.md                           数据流总说明 + 复现命令
│
└── docs/                           # 技术文档（不同于 reports 的"学习汇报"）
    └── api_contract.md                     前后端字段唯一事实源
```

## 一键启动（两端并行）

**终端 1：后端**
```bash
cd "ONI project/code/backend"
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

**终端 2：前端**
```bash
cd "ONI project/code/frontend"
npm run dev
```

打开浏览器：
- 前端 3D 页面：<http://localhost:5173/>
- 后端 Swagger UI：<http://127.0.0.1:8000/docs>

## 一键复现数据流

参见 `data/README.md` 的"一键复现流程"小节，所有脚本都用 `__file__` 推算项目根，任何工作目录下运行均可。

## 第一周交付物状态（截至 W2D1 收工）

| # | 交付物 | 状态 | 证据 |
|---|---|---|---|
| 1 | 传导链逻辑图 + ≥300 字说明 | ⏳ R1 待补 | Day 1 笔记已有概念 |
| 2 | 气象/金融名词速查 | ✅ Day 2 已交 | `reports/Day2_Learning_Report.docx` |
| 3 | 品种确认（棕榈油） | ✅ 已锁单一品种 | `reports/Day3-4_Learning_Report.docx` |
| 4 | 券商研报精华萃取 | ⏳ R3 待补（≥1 份棕榈油专题） | — |
| 5 | 气象+价格+数据源确认表 | ✅ 单品种口径达标 | `reports/Day4_*.docx` + `reports/Day5_*.docx` |
| **6** | **Python 环境 + notebook + FastAPI 最小接口** | ✅ **W2D1 已补** | `code/backend/` + `code/notebooks/01_palm_oil_eda.ipynb` |
| **7** | **react-three-fiber 3D 动态原型** | ✅ **W2D1 已补** | `code/frontend/` + 待录 30 秒 GIF |
| 8 | 阅读笔记累积 | ✅ Day2-5 已嵌入 | 各日 Learning Report |

## 第二周里程碑（W2D2 开始）

依赖刚补好的 backend 数据载入层与 notebook：

- W2D2：构造 `data/processed/product/features_palm.csv`（含 `ONI_lag_{1,3,6,9,12}`、`PRCP_lag_{3,6}`、波动率、ENSO 状态等）
- W2D3：Prophet 基线
- W2D4：XGBoost + 集成冲击 MAPE ≤ 15%
- W2D5：模型固化 + API 契约定稿（升级 `/api/meteo` 与 `/api/predict?n=N`）

详细每日卡片见 `reports/plans/Sunny_期货实习全量作战文档_..._新版.pdf` 第二部分。

## 关键技术约定

1. **字段契约唯一事实源** = `docs/api_contract.md`，任何字段重命名要在同一次提交里改双端（防 undefined）。
2. **英文术语首次出现附中文释义**，代码注释同纪律。
3. **路径相对化**：所有 Python 脚本通过 `os.path.dirname(__file__)` 定位项目根，不依赖当前工作目录。
4. **三段分类边界**：
   - `reports/` 只放可交付文档（docx/pdf），不放代码/数据
   - `code/` 只放代码（py/ts/ipynb），不放数据/报告
   - `data/` 只放数据资产（csv/png/txt），不放代码
