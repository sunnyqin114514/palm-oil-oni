# 温度深化研究与三维产量预测模型资料包说明

本资料包仅对应 2026-06-29 当天围绕以下三项任务完成的研究文档与结果附件：

1. 继续研究温度对产量的关系：优化平均积温时间长度、区分高温/低温、考察温度与降水空间交互。
2. 建立 ONI、降水、温度三维产量预测模型。
3. 模型参数基于 2010-2023 数据计算，并用 2024-2026 的预测和实际结果对比验证。

## 核心结论

推荐模型为 `M2_spatial`：

```text
Yield = α + βTrend×Trend
      + βONI×ONI_lag12
      + βPRCP×PRCP_DEV_3m
      + βTAVG×TAVG_DEV_10m
      + βINTX×INTX_West_10m
      + 月份季节项
```

其中：

- `ONI_lag12`：目标月前 12 个月 ONI。
- `PRCP_DEV_3m`：全国降水距平 3 个月滚动平均。
- `TAVG_DEV_10m`：全国气温距平 10 个月滚动平均。
- `INTX_West_10m`：西马 10 个月温度距平 × 西马 10 个月降水距平。

样本外验证窗口为 2024-01 至 2026-05。推荐模型样本外表现：

- RMSE = 0.0310
- MAPE = 7.72%
- 方向命中率 = 89.29%
- 样本外 R² = 0.529

## 文件说明

- `reports/Temperature_ONI_3D_Brief_Report.docx`：简要 Word 汇报，适合快速展示。
- `reports/Temperature_3D_Model_Report.docx`：完整 Word 报告，包含更详细的方法、表格和图。
- `data/processed/archives/00_palm_oil_research_master_malaysia.xlsx`：更新后的研究总表，包含本轮新增结果 sheet。
- `code/model/model3d_validation_metrics.csv`：三维模型与对照模型的验证指标。
- `code/model/model3d_weights.json`：推荐模型权重、系数、p 值与验证指标。
- `code/model/temp_research/`：温度窗口、高低温非对称、空间交互的结果表和图。
- `code/model/figures/model3d_validation_timeline.png`：训练拟合与样本外预测时间序列图。
- `code/model/figures/model3d_oos_detail.png`：2024-2026 样本外预测和实际结果对比图。

