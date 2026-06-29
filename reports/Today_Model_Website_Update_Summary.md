# 今日修改进度说明：温度深化研究、M2 三维模型与预测网站同步

生成时间：2026-06-29

## 1. 当前网站实际使用的模型

当前预测网站已同步到今天最新的 **M2_spatial** 三维产量预测模型。

模型结构：

```text
Yield_pred
= Intercept
+ Trend
+ Seasonality(month dummy)
+ beta_ONI  × ONI_lag12
+ beta_PRCP × PRCP_DEV_3m
+ beta_TAVG × TAVG_DEV_10m
+ beta_INTX × INTX_West_10m
```

其中：

- `ONI_lag12`：12 个月前的 ONI（厄尔尼诺背景信号）。
- `PRCP_DEV_3m`：全国降水距平的 3 个月滚动平均。
- `TAVG_DEV_10m`：全国气温距平的 10 个月滚动平均。
- `INTX_West_10m`：西马 10 个月温度距平 × 西马 10 个月降水距平，表示西马温度与降水的空间交互项。

当前权重文件：

```text
code/model/model3d_weights.json
```

核心系数：

| 因子 | 系数 | p值 | 说明 |
|---|---:|---:|---|
| ONI_lag12 | -0.003272 | 0.3318 | 符号为负，符合厄尔尼诺后续减产逻辑 |
| PRCP_DEV_3m | -0.000168 | 0.0183 | 降水项显著 |
| TAVG_DEV_10m | -0.009223 | 0.5598 | 温度主效应弱 |
| INTX_West_10m | +0.001002 | 0.0227 | 西马温降交互显著 |

## 2. 模型验证结果

训练窗口：

```text
2010-01 ~ 2023-12
```

样本外验证窗口：

```text
2024-01 ~ 2026-05
```

推荐模型 `M2_spatial / full` 的样本外指标：

| 指标 | 数值 |
|---|---:|
| RMSE | 0.0310 |
| MAE | 0.0251 |
| MAPE | 7.72% |
| 方向命中率 | 89.29% |
| 样本外 R² | 0.529 |

模型对比文件：

```text
code/model/model3d_validation_metrics.csv
```

## 3. 今天新增/完善的计算链路

### 3.1 数据与特征

- 补齐全马格点气象数据，覆盖婆罗洲（沙巴/砂拉越）与西马。
- 构建西马、砂拉越、沙巴三区月度气象序列。
- 构建扩展数据集到 2010-2026。
- 构建候选特征表 `palm_oil_features.csv`，包含温度窗口、非对称温度、三区温降交互等特征。

关键文件：

```text
data/processed/meteo/nasa_power_grid_full_malaysia_monthly.csv
data/processed/meteo/malaysia_regional_weather_monthly.csv
data/processed/meteo/malaysia_regional_weather_wide.csv
data/processed/product/palm_oil_extended_dataset.csv
data/processed/product/palm_oil_features.csv
```

### 3.2 温度研究

完成三类温度研究：

1. 积温窗口：搜索 1~12 月窗口，10 月窗口最接近显著。
2. 高温/低温非对称：偏热项比偏冷项更接近显著，说明温度影响主要来自热胁迫。
3. 温度×降水空间交互：西马温×降交互显著，样本外误差显著下降。

关键文件：

```text
code/model/temperature_analysis.py
code/model/temp_research/dim_a_window.csv
code/model/temp_research/dim_b_asymmetry.csv
code/model/temp_research/dim_c_spatial.csv
code/model/temp_research/summary.md
```

### 3.3 三维模型

完成三套模型对比：

- `M0_baseline`：ONI + 3月降水 + 3月温度。
- `M1_3factor`：ONI + 3月降水 + 10月温度。
- `M2_spatial`：M1 + 西马温×降交互。

最终推荐：

```text
M2_spatial = ONI_lag12 + PRCP_DEV_3m + TAVG_DEV_10m + INTX_West_10m
```

关键文件：

```text
code/model/build_3factor_model.py
code/model/model3d_weights.json
code/model/model3d_validation_metrics.csv
code/model/figures/model3d_validation_timeline.png
code/model/figures/model3d_oos_detail.png
```

## 4. 网站同步状态

### 4.1 后端预测接口

后端预测入口：

```text
code/model/predict.py
code/backend/app/core/predict_service.py
code/backend/app/main.py
```

当前后端已优先读取：

```text
code/model/model3d_weights.json
```

如果 `model3d_weights.json` 不存在，才回退旧版：

```text
code/model/model_weights.json
```

实测接口返回：

```text
model_name = M2_spatial
features = ONI_lag12, PRCP_DEV_3m, TAVG_DEV_10m, INTX_West_10m
contributions = intercept, trend, ONI, PRCP, TAVG, INTX_West, seasonality
```

### 4.2 首页

首页已同步：

- 公式改为 M2 三维模型。
- 贡献表新增 `西马温×降交互`。
- 去除了“可信度/精度”展示。

文件：

```text
code/backend/app/static/index.html
```

### 4.3 3D 柱状图

3D 柱状图已同步：

- 柱高 = 预测产量。
- 柱身主色 = 当月主导影响因子。
- 四条光带 = ONI、降水、10月温度、西马温×降交互的贡献强弱。
- 光带前侧表示拉高产量，后侧表示拉低产量。
- tooltip 显示主导因子、四个贡献项和三个输入特征。
- 去除了“可信度/精度”展示。

文件：

```text
code/backend/app/static/scene3d.html
```

### 4.4 启动脚本

修复了项目移动路径后 `.command` 打不开的问题。

当前启动脚本会根据自身所在目录定位后端，不再写死旧路径。

文件：

```text
启动后端.command
```

## 5. 运行验证结果

已运行以下验证：

```text
/predict-production?target_month=2026-06
/predict-production-range?start_month=2026-06&months=3
```

返回结果确认：

```text
ONE model: M2_spatial
features: ['ONI_lag12', 'PRCP_DEV_3m', 'TAVG_DEV_10m', 'INTX_West_10m']
inputs: prcp_dev_3m / tavg_dev_10m / intx_west_10m 均正常返回
contributions: INTX_West 已包含在贡献拆分中
```

同时完成：

```text
python -m py_compile
ReadLints
```

均未发现错误。

## 6. 展示建议

展示时建议按这个顺序说明：

1. 先说模型从旧版 `3月温度` 升级到 `10月温度 + 西马温降交互`。
2. 再展示 `Temperature_3D_Model_Report.docx` 中的样本外验证图。
3. 然后打开网站首页，预测一个月份，展示贡献拆分。
4. 最后打开 3D 柱状图，说明每根柱子的主导因子和四条光带代表什么。

