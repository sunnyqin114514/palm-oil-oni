# -*- coding: utf-8 -*-
"""
day8_fetch_ifind_edb.py — 从同花顺 iFinD HTTP API 抓取 EDB（经济数据库）指标。

特性：
  - refresh_token 与 access_token 缓存在 ~/.cache/ifind/tokens.json（chmod 600），永不进 git
  - access_token 过期或被服务端拒绝时（errorcode -1306/-1301 等）自动用 refresh_token 续期一次
  - 一次可抓多个指标（半角逗号分隔的 indicators），自动 join 成长表 (DATE, ID, INDEX_NAME, VALUE)
  - 默认输出到 data/raw/product/ifind_edb_<slug>.csv，slug 由 indicators+日期范围生成

用法示例：
  # 把 refresh_token 一次性写入缓存（首次配置时使用）
  python code/scripts/day8_fetch_ifind_edb.py --set-refresh-token "eyJ..."

  # 抓某指标
  python code/scripts/day8_fetch_ifind_edb.py \
      --indicators M001620326 \
      --start 2015-01-01 --end 2026-06-30 \
      --slug gdp_demo

  # 抓多个指标
  python code/scripts/day8_fetch_ifind_edb.py \
      --indicators M00xxxxxxx,M00yyyyyyy \
      --start 2007-01-01 --end 2026-06-30 \
      --slug palm_oil_production_my
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import urllib.request
import urllib.error


HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
DATA_RAW = PROJECT_ROOT / "data" / "raw" / "product"

CACHE_DIR = Path.home() / ".cache" / "ifind"
TOKEN_FILE = CACHE_DIR / "tokens.json"

GET_ACCESS_TOKEN_URL = "https://quantapi.51ifind.com/api/v1/get_access_token"
EDB_URL = "https://quantapi.51ifind.com/api/v1/edb_service"


# ── token 缓存读写 ──────────────────────────────────────────────────────────────

def _read_tokens() -> dict:
    if not TOKEN_FILE.exists():
        return {}
    try:
        return json.loads(TOKEN_FILE.read_text())
    except Exception as e:
        print(f"[warn] 读取 token 缓存失败: {e}", file=sys.stderr)
        return {}


def _write_tokens(d: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(CACHE_DIR, 0o700)
    TOKEN_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    os.chmod(TOKEN_FILE, 0o600)


def set_refresh_token(rt: str) -> None:
    """首次配置：把 refresh_token 写入缓存。"""
    if not rt or "." not in rt:
        raise ValueError("refresh_token 看起来不像合法字符串 (应包含 '.' 分段)")
    d = _read_tokens()
    d["refresh_token"] = rt.strip()
    _write_tokens(d)
    print(f"[ok] refresh_token 已写入 {TOKEN_FILE}")


# ── HTTP 工具 ────────────────────────────────────────────────────────────────────

def _post_json(url: str, headers: dict, payload: dict | None = None,
               timeout: int = 30) -> dict:
    body = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    for k, v in headers.items():
        req.add_header(k, v)
    req.add_header("Content-Type", "application/json")
    req.add_header("Content-Length", str(len(body)))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return {"errorcode": -9999, "errmsg": f"non-JSON response: {raw[:200]!r}"}


# ── token 刷新 ──────────────────────────────────────────────────────────────────

def refresh_access_token() -> str:
    d = _read_tokens()
    rt = d.get("refresh_token")
    if not rt:
        raise SystemExit(
            "[fatal] 缓存里没有 refresh_token。请先运行：\n"
            "    python code/scripts/day8_fetch_ifind_edb.py --set-refresh-token \"eyJ...\""
        )
    resp = _post_json(GET_ACCESS_TOKEN_URL, {"refresh_token": rt}, {})
    if resp.get("errorcode") != 0:
        raise SystemExit(
            f"[fatal] 换 access_token 失败: errorcode={resp.get('errorcode')} "
            f"msg={resp.get('errmsg')}"
        )
    info = resp["data"]
    d["access_token"] = info["access_token"]
    d["access_token_expired_time"] = info.get("expired_time", "")
    _write_tokens(d)
    print(f"[ok] access_token 已更新，过期: {d['access_token_expired_time']}")
    return d["access_token"]


def get_access_token(force_refresh: bool = False) -> str:
    d = _read_tokens()
    at = d.get("access_token") if not force_refresh else None
    if at:
        return at
    return refresh_access_token()


# ── EDB 拉数 ────────────────────────────────────────────────────────────────────

def call_edb(indicators: str, start: str, end: str) -> dict:
    """两段式调用：access_token 过期时自动续期重试一次。"""
    payload = {
        "indicators": indicators,
        "startdate": start,
        "enddate": end,
    }
    for attempt in (1, 2):
        at = get_access_token(force_refresh=(attempt == 2))
        resp = _post_json(EDB_URL, {"access_token": at}, payload)
        ec = resp.get("errorcode")
        if ec == 0:
            return resp
        if attempt == 1 and ec in (-1302, -1306, -1308):
            print(f"[info] access_token 失效 (errorcode={ec})，自动续期重试...")
            continue
        raise SystemExit(
            f"[fatal] EDB 调用失败: errorcode={ec} msg={resp.get('errmsg')}"
        )
    raise SystemExit("[fatal] EDB 调用失败（不应到此）")


# ── 结果转长表 CSV ─────────────────────────────────────────────────────────────

def to_long_csv(resp: dict, out_path: Path) -> int:
    """
    iFinD EDB 返回结构：
      tables: [
        { id: [...], time: [...], value: [...], rtime: [...], index_name: [...] },
        ...一个指标一个 table
      ]
    转长表：DATE, ID, INDEX_NAME, VALUE, RTIME
    """
    tables = resp.get("tables") or []
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for t in tables:
        ids = t.get("id") or []
        times = t.get("time") or []
        vals = t.get("value") or []
        rtimes = t.get("rtime") or []
        names = t.get("index_name") or []
        n = max(len(times), len(vals))
        default_id = ids[0] if ids else ""
        default_name = names[0] if names else ""
        for i in range(n):
            rows.append({
                "DATE": times[i] if i < len(times) else "",
                "ID": ids[i] if i < len(ids) else default_id,
                "INDEX_NAME": names[i] if i < len(names) else default_name,
                "VALUE": vals[i] if i < len(vals) else "",
                "RTIME": rtimes[i] if i < len(rtimes) else "",
            })

    import csv
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["DATE", "ID", "INDEX_NAME", "VALUE", "RTIME"])
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return len(rows)


# ── 主入口 ──────────────────────────────────────────────────────────────────────

def _safe_slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_]+", "_", s).strip("_").lower()
    return s or "edb"


def main():
    ap = argparse.ArgumentParser(description="iFinD EDB fetcher")
    ap.add_argument("--set-refresh-token", dest="set_rt", default=None,
                    help="把 refresh_token 写入 ~/.cache/ifind/tokens.json")
    ap.add_argument("--indicators", default=None,
                    help="半角逗号分隔的指标编号，例如 M001620326,M002822183")
    ap.add_argument("--start", default=None, help="开始日期 YYYY-MM-DD")
    ap.add_argument("--end", default=None, help="结束日期 YYYY-MM-DD")
    ap.add_argument("--slug", default=None,
                    help="输出文件命名标记，默认按指标自动生成")
    ap.add_argument("--out-dir", default=str(DATA_RAW),
                    help="输出目录，默认 data/raw/product/")
    args = ap.parse_args()

    if args.set_rt:
        set_refresh_token(args.set_rt)
        return

    if not (args.indicators and args.start and args.end):
        ap.error("必须提供 --indicators / --start / --end，或先用 --set-refresh-token 配置")

    slug = args.slug or _safe_slug(args.indicators)
    out_path = Path(args.out_dir) / f"ifind_edb_{slug}.csv"

    t0 = time.time()
    print(f"[fetch] indicators={args.indicators}  range={args.start}~{args.end}")
    resp = call_edb(args.indicators, args.start, args.end)
    n = to_long_csv(resp, out_path)
    dt = (time.time() - t0) * 1000

    meta = {
        "perf_ms_server": resp.get("perf"),
        "dataVol": resp.get("dataVol"),
        "elapsed_ms_local": int(dt),
        "rows_written": n,
        "out": str(out_path),
    }
    print(f"[ok] {n} rows -> {out_path}")
    print(f"[meta] {json.dumps(meta, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
