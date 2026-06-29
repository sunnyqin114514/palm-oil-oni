"""预测服务桥接层 (prediction service bridge)。

把 code/model/predict.py 的预测引擎接到 FastAPI。
后端 API 真正算数的入口就是这里, 它只负责调用模型引擎并做防御性封装,
不在这里重写任何回归/统计逻辑。
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from typing import List

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(HERE))
CODE_DIR = os.path.dirname(BACKEND_DIR)
MODEL_DIR = os.path.join(CODE_DIR, "model")

if MODEL_DIR not in sys.path:
    sys.path.insert(0, MODEL_DIR)

import predict as model_predict  # noqa: E402  (路径注入后才能导入)


@lru_cache(maxsize=1)
def _weights() -> dict:
    """缓存模型权重, 避免每次请求重复读盘。"""
    return model_predict.load_weights()


@lru_cache(maxsize=1)
def _context() -> dict:
    """缓存气候上下文 (三本 Excel 读取结果)。"""
    return model_predict.load_climate_context()


def predict_one(target_month: str) -> dict:
    """预测单个目标月。异常向上抛, 由 API 层转成 HTTP 错误。"""
    return model_predict.predict_future_production(
        target_month,
        weights=_weights(),
        context=_context(),
    )


def predict_many(start_month: str, n_months: int) -> List[dict]:
    """连续预测 n_months 个月, 复用同一份权重与上下文。"""
    if n_months < 1:
        raise ValueError("n_months 必须 >= 1")
    weights = _weights()
    context = _context()
    return [
        model_predict.predict_future_production(
            model_predict._shift_month(start_month, i),
            weights=weights,
            context=context,
        )
        for i in range(n_months)
    ]


def clear_cache() -> None:
    """上传新的气候预测文件后清理缓存, 让后续预测读取最新 Excel。"""
    _weights.cache_clear()
    _context.cache_clear()
