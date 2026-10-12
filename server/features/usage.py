"""BYOK token usage: every call to your own model is appended to `data/usage.jsonl`.

The recorder wraps the two places where agent_bridge talks to a model:
`_post_json` (openai_compatible and http drivers) and `_cli` (cli driver), so
Copilot, triage, skills and /api/v1/agent/run are all counted without editing
them. Token counts come from the provider's `usage` block when it returns one;
otherwise they are estimated (CJK char = 1 token, other text = 4 chars per
token) and the entry is marked `estimated`. Only counts and metadata are kept:
never the prompt, the answer, the endpoint path or any API key.

    GET  /api/usage?days=30&limit=50   totals, per driver/model/feature/day, recent calls
    POST /api/usage/clear              truncate the log
"""
from __future__ import annotations

import contextlib
import contextvars
import json
import re
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

import agent_bridge
import yhbmail
from features import get, post
from features._origin import local_origin, refuse

USAGE_PATH: Path = yhbmail.DATA / "usage.jsonl"
CJK_RE = re.compile(r"[\u3000-\u9fff\uac00-\ud7af\uf900-\ufaff\uff00-\uffef]")
_lock = threading.Lock()
_feature: contextvars.ContextVar[str] = contextvars.ContextVar("tpi_usage_feature", default="")

# function name in the call stack -> feature label, for callers that do not set a scope
CALLERS = {
    "run_copilot": "copilot",
    "agent_summarize": "triage:summary",
    "digest_with_agent": "triage:digest",
    "run_agent": "agent",
}


def estimate_tokens(text) -> int:
    if not text:
        return 0
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False)
    cjk = len(CJK_RE.findall(text))
    rest = len(text) - cjk
    return cjk + (rest + 3) // 4


@contextlib.contextmanager
def scope(feature: str):
    """Attribute model calls made inside the block to `feature` (e.g. "skills:morning-brief")."""
    token = _feature.set(feature)
    try:
        yield
    finally:
        _feature.reset(token)


def current_feature() -> str:
    label = _feature.get()
    if label:
        return label
    frame = sys._getframe(1)
    while frame is not None:
        hit = CALLERS.get(frame.f_code.co_name)
        if hit:
            return hit
        frame = frame.f_back
    return "other"


def record(driver: str, model: str = "", prompt_tokens: int = 0, completion_tokens: int = 0,
           estimated: bool = True, ok: bool = True, feature: str = "", host: str = "",
           ms: int = 0, error: str = "") -> dict:
    entry = {
        "ts": yhbmail.now_iso(),
        "feature": feature or current_feature(),
        "driver": driver or "unknown",
        "model": (model or "")[:80],
        "host": (host or "")[:120],
        "prompt_tokens": max(0, int(prompt_tokens or 0)),
        "completion_tokens": max(0, int(completion_tokens or 0)),
        "estimated": bool(estimated),
        "ok": bool(ok),
        "ms": max(0, int(ms or 0)),
    }
    entry["total_tokens"] = entry["prompt_tokens"] + entry["completion_tokens"]
    if error:
        entry["error"] = str(error)[:200]
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        USAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
        with USAGE_PATH.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    return entry


def read_entries() -> list[dict]:
    if not USAGE_PATH.exists():
        return []
    out = []
    with _lock:
        lines = USAGE_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("ts"):
            out.append(row)
    return out


def clear() -> int:
    n = len(read_entries())
    with _lock:
        if USAGE_PATH.exists():
            USAGE_PATH.write_text("", encoding="utf-8")
    return n


# ───────────────────────── wrappers around the model chokepoints ─────────────────────────

def _usage_numbers(data) -> tuple[int, int] | None:
    u = data.get("usage") if isinstance(data, dict) else None
    if not isinstance(u, dict):
        return None
    p = u.get("prompt_tokens", u.get("input_tokens"))
    c = u.get("completion_tokens", u.get("output_tokens"))
    if not isinstance(p, (int, float)) and not isinstance(c, (int, float)):
        return None
    return int(p or 0), int(c or 0)


def _answer_text(data) -> str:
    if not isinstance(data, dict):
        return ""
    try:
        return data["choices"][0]["message"]["content"] or ""
    except (KeyError, IndexError, TypeError):
        return str(data.get("answer") or data.get("text") or "")


def _wrap_post_json(orig):
    def _post_json(url, headers, body, timeout=90, allow_private=False):
        try:
            payload = json.loads(body.decode() if isinstance(body, bytes) else body)
        except (ValueError, UnicodeDecodeError):
            payload = {}
        chat = isinstance(payload, dict) and isinstance(payload.get("messages"), list)
        driver = "openai_compatible" if chat else "http"
        model = str(payload.get("model") or "") if chat else ""
        prompt = payload.get("messages") if chat else payload
        host = urllib.parse.urlsplit(str(url)).hostname or ""
        feature = current_feature()
        started = time.monotonic()
        try:
            data = orig(url, headers, body, timeout=timeout, allow_private=allow_private)
        except Exception as e:
            record(driver, model, estimate_tokens(prompt), 0, True, False, feature, host,
                   int((time.monotonic() - started) * 1000), f"{type(e).__name__}: {e}")
            raise
        nums = _usage_numbers(data)
        if nums:
            p, c, est = nums[0], nums[1], False
        else:
            p, c, est = estimate_tokens(prompt), estimate_tokens(_answer_text(data)), True
        if isinstance(data, dict) and data.get("model") and chat:
            model = str(data["model"])
        record(driver, model, p, c, est, True, feature, host, int((time.monotonic() - started) * 1000))
        return data
    _post_json.__wrapped__ = orig
    _post_json.__tpi_usage__ = True
    return _post_json


def _wrap_cli(orig):
    def _cli(pack, cfg):
        block = (cfg or {}).get("cli") or {}
        cmd = block.get("command") or ["claude", "-p"]
        model = str(block.get("model") or Path(str(cmd[0])).name)
        prompt = json.dumps(pack, ensure_ascii=False)[:24000]
        feature = current_feature()
        started = time.monotonic()
        try:
            out = orig(pack, cfg)
        except Exception as e:
            record("cli", model, estimate_tokens(prompt), 0, True, False, feature, "",
                   int((time.monotonic() - started) * 1000), f"{type(e).__name__}: {e}")
            raise
        record("cli", model, estimate_tokens(prompt), estimate_tokens(out), True, True, feature, "",
               int((time.monotonic() - started) * 1000))
        return out
    _cli.__wrapped__ = orig
    _cli.__tpi_usage__ = True
    return _cli


def install() -> None:
    if not getattr(agent_bridge._post_json, "__tpi_usage__", False):
        agent_bridge._post_json = _wrap_post_json(agent_bridge._post_json)
    if not getattr(agent_bridge._cli, "__tpi_usage__", False):
        agent_bridge._cli = _wrap_cli(agent_bridge._cli)


install()


# ───────────────────────── report ─────────────────────────

def _zh(lang) -> bool:
    return str(lang or "").lower().startswith("zh")


def _empty() -> dict:
    return {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
            "estimated_calls": 0, "errors": 0}


def _add(acc: dict, row: dict) -> None:
    acc["calls"] += 1
    for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
        acc[k] += int(row.get(k) or 0)
    acc["estimated_calls"] += 1 if row.get("estimated") else 0
    acc["errors"] += 0 if row.get("ok", True) else 1


def _group(rows: list[dict], key) -> list[dict]:
    groups: dict[str, dict] = {}
    for r in rows:
        k = key(r)
        g = groups.setdefault(k, {"key": k, **_empty()})
        _add(g, r)
    return sorted(groups.values(), key=lambda g: (-g["total_tokens"], -g["calls"], g["key"]))


def _parse_ts(raw: str):
    try:
        return datetime.fromisoformat(str(raw))
    except ValueError:
        return None


def report(days: int = 30, limit: int = 50, lang: str = "en", now=None) -> dict:
    zh = _zh(lang)
    rows = read_entries()
    ref = now or datetime.now(yhbmail.TZ)
    floor = ref - timedelta(days=days)
    window = []
    for r in rows:
        ts = _parse_ts(r["ts"])
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=yhbmail.TZ)
        if ts >= floor:
            window.append(r)
    totals = _empty()
    for r in window:
        _add(totals, r)
    all_time = _empty()
    for r in rows:
        _add(all_time, r)
    by_day = sorted(_group(window, lambda r: str(r["ts"])[:10]), key=lambda g: g["key"])
    driver = agent_bridge.load_agent_cfg().get("driver") or "local"
    if driver == "local":
        note = ("目前 agent.json 的 driver 是 local（本機規則），不會呼叫模型，也不會產生用量。"
                if zh else "agent.json driver is local (rules only): no model is called and nothing is counted.")
    else:
        note = (f"目前走 BYO agent（{driver}）。有回傳 usage 的端點記實數，其餘依字數估算並標「估」。"
                if zh else f"Using BYO agent ({driver}). Endpoints that return usage are exact; the rest are estimated.")
    return {
        "file": str(USAGE_PATH.relative_to(yhbmail.ROOT)) if USAGE_PATH.is_relative_to(yhbmail.ROOT) else str(USAGE_PATH),
        "days": days,
        "totals": totals,
        "all_time": all_time,
        "by_driver": _group(window, lambda r: r.get("driver") or "unknown"),
        "by_model": _group(window, lambda r: f"{r.get('driver') or '?'} · {r.get('model') or '?'}"),
        "by_feature": _group(window, lambda r: r.get("feature") or "other"),
        "by_day": by_day,
        "recent": list(reversed(window))[:limit],
        "driver_now": driver,
        "note": note,
        "lang": "zh-Hant" if zh else "en",
    }


def _int(value, default: int, lo: int = 1, hi: int = 3650) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


@get("/api/usage")
def usage_report(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    return report(_int(req.query.get("days"), 30), _int(req.query.get("limit"), 50, hi=500),
                  "zh-Hant" if req.lang_zh() else "en")


@post("/api/usage/clear")
def usage_clear(req):
    if not local_origin(req):
        return refuse(req.lang_zh())
    n = clear()
    note = f"已清除 {n} 筆用量紀錄。" if req.lang_zh() else f"Cleared {n} usage entries."
    return {"ok": True, "cleared": n, "note": note}
