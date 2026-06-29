"""DeepSeek 解读层 (LLM explanation)。

职责单一: 把后端线性模型已经算好的结构化预测结果, 交给 DeepSeek 翻译成
中文人话解读。DeepSeek 不负责产生任何预测数字, 只解释既有数字。

设计要点 (符合防御性编程):
  - API Key 从环境变量 DEEPSEEK_API_KEY 读取 (支持 .env)。
  - 没有 Key 或调用失败时, 自动降级为本地规则解读, 网站照常可用。
  - 所有网络调用包裹 try/except + 超时, 失败有日志和明确降级策略。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

logger = logging.getLogger("palm.llm")

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.dirname(os.path.dirname(HERE))
CODE_DIR = os.path.dirname(BACKEND_DIR)
PROJECT_ROOT = os.path.dirname(CODE_DIR)

# 依次尝试加载 backend/.env 与项目根 .env, 已存在的环境变量不被覆盖。
for _env_path in (
    os.path.join(BACKEND_DIR, ".env"),
    os.path.join(PROJECT_ROOT, ".env"),
):
    if os.path.exists(_env_path):
        load_dotenv(_env_path, override=False)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "").strip()
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_TIMEOUT = float(os.getenv("DEEPSEEK_TIMEOUT", "30"))

LLM_SOURCE_DEEPSEEK = "deepseek"
LLM_SOURCE_LOCAL = "local_rule_based_fallback"

_WEATHER_SOURCE_CN = {
    "ecmwf_seasonal_forecast": "ECMWF 季节预报",
    "ecmwf_with_baseline_fallback": "ECMWF 预报（部分月份用历史常态补齐）",
    "observed_history": "历史实测天气",
    "seasonal_climatology_baseline": "历史同期常态（基准情形）",
    "mixed_history_and_baseline": "历史实测与基准常态混合",
}


def _fmt(value: float, digits: int = 4) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _weather_cn(source: str) -> str:
    return _WEATHER_SOURCE_CN.get(source, source)


def build_local_explanation(prediction: dict) -> str:
    """不依赖外部 API 的本地规则解读, 作为 DeepSeek 不可用时的兜底。"""
    contrib = prediction.get("contributions", {}) or {}
    inputs = prediction.get("inputs", {}) or {}
    target = prediction.get("target_month", "目标月")
    yield_pred = prediction.get("predicted_yield")
    tonnes = prediction.get("predicted_production_tonnes")
    weather = _weather_cn(prediction.get("weather_source", ""))

    items = [
        ("季节性（月份效应）", contrib.get("seasonality", 0.0)),
        ("结构性趋势", contrib.get("trend", 0.0)),
        ("厄尔尼诺 ONI", contrib.get("ONI", 0.0)),
        ("降水距平", contrib.get("PRCP", 0.0)),
        ("10月气温距平", contrib.get("TAVG", 0.0)),
        ("西马温度×降水交互", contrib.get("INTX_West", 0.0)),
    ]
    ranked = sorted(items, key=lambda kv: abs(kv[1]), reverse=True)

    lines = [
        f"【{target} 棕榈油产量预测解读】",
        f"预测单产约 {_fmt(yield_pred)} 吨/公顷，还原为总产量约 {_fmt(tonnes, 0)} 吨。",
        f"天气依据：{weather}。",
        "",
        "各因素对单产的影响（按影响大小排序）：",
    ]
    for name, val in ranked:
        direction = "拉高" if val > 0 else ("拉低" if val < 0 else "基本无影响")
        lines.append(f"  · {name}：{direction} {_fmt(abs(val))} 吨/公顷")

    oni_ref = inputs.get("oni_reference_month")
    oni_val = inputs.get("oni_value")
    if oni_ref is not None:
        lines.append("")
        lines.append(
            f"说明：ONI 用的是 {oni_ref} 的真实值（{_fmt(oni_val, 2)}），"
            "因为厄尔尼诺对油棕产量的影响通常滞后约一年才显现。"
        )
    return "\n".join(lines)


def _build_prompt(prediction: dict) -> str:
    """构造给 DeepSeek 的提示词, 强调只解释、不得编造数字。"""
    import json

    payload = json.dumps(prediction, ensure_ascii=False, indent=2)
    return (
        "你是一名马来西亚棕榈油产业分析师。下面是一个线性回归模型已经算好的"
        "某个月棕榈油产量预测结果（JSON）。请你用简洁中文向投研同事解读：\n"
        "1. 这个月预测单产和总产量大概是多少；\n"
        "2. 哪些因素在拉高、哪些在拉低产量，按影响大小说明；\n"
        "3. 天气数据来源说明（ECMWF 预报还是历史常态基准）对结论可信度的含义；\n"
        "4. 给出一句话风险提示。\n\n"
        "严格要求：只能解释下方 JSON 里已有的数字，禁止编造任何新数据或新预测值。\n"
        "用词通俗，控制在 250 字以内。\n\n"
        f"预测结果 JSON：\n{payload}"
    )


def explain_prediction(prediction: dict) -> dict:
    """把预测结果交给 DeepSeek 解读; 不可用时降级为本地解读。"""
    local_text = build_local_explanation(prediction)

    if not DEEPSEEK_API_KEY:
        logger.info("DEEPSEEK_API_KEY 未配置，使用本地规则解读降级。")
        return {
            "explanation": local_text,
            "llm_source": LLM_SOURCE_LOCAL,
            "note": "未配置 DEEPSEEK_API_KEY，已使用本地规则解读。",
        }

    try:
        resp = httpx.post(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "你是严谨的棕榈油产业分析师，只解释给定数据，不编造数字。",
                    },
                    {"role": "user", "content": _build_prompt(prediction)},
                ],
                "temperature": 0.3,
                "stream": False,
            },
            timeout=DEEPSEEK_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        content = (
            data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        )
        if not content:
            raise ValueError("DeepSeek 返回内容为空")
        return {"explanation": content, "llm_source": LLM_SOURCE_DEEPSEEK, "note": ""}
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("DeepSeek 调用失败，降级本地解读：%s", exc)
        return {
            "explanation": local_text,
            "llm_source": LLM_SOURCE_LOCAL,
            "note": f"DeepSeek 调用失败已降级：{exc}",
        }
