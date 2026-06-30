FINAL RESEARCH PACKAGE (2026-06-29)
====================================

This package contains materials for the 2026-06-29 research update only.
It does NOT include website frontend/backend files or startup scripts.

What this update answers (mentor's three requirements):
  1. Optimize cumulative temperature window length.
  2. Test heat-only vs cold-only temperature effect.
  3. Temperature x precipitation spatial interaction.
  Plus: build an ONI + precipitation + temperature 3D prediction model,
        train on 2010-2023 and validate on 2024-2026 actuals.

Recommended reading order:
  1. 01_Report/Main_Brief_Report.docx  -- the only file you must read
  2. 02_Figures/Fig1_Temperature_Window_Search.png
  3. 02_Figures/Fig2_Heat_Cold_Asymmetry.png
  4. 02_Figures/Fig3_Spatial_Interaction.png
  5. 02_Figures/Fig5_OOS_2024_2026_Detail.png
  6. 03_Tables/Model_Validation_Metrics.csv
  7. 05_Model/M2_spatial_Model_Weights.json

Folder guide:
  00_Readme  -- this guide
  01_Report  -- one main Word report (concise, with 4 embedded figures)
  02_Figures -- key figures for presentation
  03_Tables  -- result tables (window search, asymmetry, spatial, validation)
  04_Data    -- processed datasets and master workbook
  05_Model   -- recommended model weights (M2_spatial)
  06_Code    -- scripts that produced the research outputs

Main model:
  M2_spatial = ONI_lag12 + PRCP_DEV_3m + TAVG_DEV_10m + INTX_West_10m
               + Trend + monthly seasonality

Training window:  2010-01 to 2023-12 (168 months, includes 2010-2014 area backcast)
Validation window: 2024-01 to 2026-05 (28 months, out-of-sample)
Best OOS RMSE:        0.0310
MAPE:                 7.72%
Direction hit rate:   89.29%

Data modifications made for this study:
  - Re-fetched NASA POWER full-Malaysia grid (lon 99.375-119.5, lat 0.5-7.5)
    to cover Borneo (Sarawak/Sabah), 2007-2025 monthly + 2026 daily aggregated.
  - Built West/Sarawak/Sabah regional monthly series with land masking.
  - Extended MPOB mature area: 2010-2014 linear backcast, 2026 3-year trend forecast.
