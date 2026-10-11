#!/usr/bin/env python3
"""TooPowerInbox MCP server (stdio, JSON-RPC 2.0, newline-delimited).

Exposes agent_bridge.TOOLS to any MCP client (Claude Desktop, Cursor, ...).
Read-only over the local cache, plus save_draft which only writes a local
draft row. Nothing here talks to a mail provider or the network.

Run:  python3 server/mcp_server.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
os.environ.setdefault("OPENINBOX_ROOT", str(HERE.parent))
sys.path.insert(0, str(HERE))

import agent_bridge  # noqa: E402
import yhbmail  # noqa: E402

SERVER_NAME = "toopowerinbox"
SERVER_VERSION = "0.1.0"
SUPPORTED_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_VERSION = SUPPORTED_VERSIONS[0]

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

MAX_TEXT = 20000

INSTRUCTIONS = (
    "TooPowerInbox local inbox brain. Tools read the local mail cache, triage board, "
    "Second Brain cards and persona. save_draft stores a local draft only; nothing is ever sent.\n"
    "TooPowerInbox 本機信箱大腦。工具只讀本機快取的信件、分流看板、第二大腦卡片與個人輪廓；"
    "save_draft 只存本機草稿，絕不寄出。"
)

READ_ONLY = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False}

TOOL_SPECS: dict[str, dict] = {
    "list_inbox": {
        "title": "List inbox / 列出收件匣",
        "description": (
            "List recent mail from the local cache, newest first. "
            "列出本機快取的近期信件（新到舊）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Text filter on subject/snippet/from/body. 關鍵字篩選。"},
                "category": {
                    "type": "string",
                    "enum": ["all", "needs_you", "upcoming", "worth_a_look", "fyi", "other"],
                    "description": "Triage bucket. 分流類別。",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20,
                          "description": "Max rows. 最多筆數。"},
            },
            "additionalProperties": False,
        },
        "annotations": READ_ONLY,
    },
    "brain_board": {
        "title": "Triage board / 分流看板",
        "description": (
            "Five-bucket triage board (needs you, upcoming, worth a look, FYI, other) for the last N hours. "
            "近 N 小時的五格分流看板（需要你、即將到來、值得一看、知悉、其他）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "minimum": 1, "maximum": 8760, "default": 168,
                          "description": "Look-back window in hours. 回溯小時數。"},
            },
            "additionalProperties": False,
        },
        "annotations": READ_ONLY,
    },
    "search_brain": {
        "title": "Search Second Brain / 搜尋第二大腦",
        "description": (
            "Search Second Brain cards distilled from mail and calendar. Empty q returns all cards. "
            "搜尋由信件與行事曆整理出的第二大腦卡片；q 留空回傳全部。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "q": {"type": "string", "description": "Search text. 搜尋字串。"},
            },
            "additionalProperties": False,
        },
        "annotations": READ_ONLY,
    },
    "persona": {
        "title": "Know you better / 更了解你",
        "description": (
            "Read the know-you-better profile: writing habits, inbox rules, attention now, top senders. "
            "讀取「更了解你」輪廓：文風、收信習慣、此刻重點、常見寄件人。"
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "annotations": READ_ONLY,
    },
    "save_draft": {
        "title": "Save local draft / 存本機草稿",
        "description": (
            "Store a reply as a local draft in the TooPowerInbox database. Never sends anything. "
            "把回信存成本機草稿，絕不寄出。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Recipient (stored only). 收件人（僅記錄）。"},
                "subject": {"type": "string", "description": "Subject. 主旨。"},
                "body": {"type": "string", "description": "Draft body. 草稿內文。"},
                "account": {"type": "string", "description": "Account label, default you@example.com. 帳號。"},
                "lang": {"type": "string", "enum": ["en", "zh-Hant"], "default": "en",
                         "description": "Language of the returned note. 回覆語言。"},
            },
            "required": ["subject", "body"],
            "additionalProperties": False,
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False,
                        "idempotentHint": False, "openWorldHint": False},
    },
}

_TYPES = {"string": str, "integer": int, "object": dict}


class ToolArgError(ValueError):
    pass


def mcp_tools() -> list[dict]:
    """MCP tool descriptors, one per agent_bridge.TOOLS entry, in the same order."""
    out = []
    for t in agent_bridge.TOOLS:
        spec = TOOL_SPECS.get(t["name"])
        if spec is None:
            spec = {"title": t["name"], "description": t.get("description") or "",
                    "inputSchema": {"type": "object"}}
        out.append({"name": t["name"], **spec})
    return out


def validate_args(name: str, args) -> dict:
    if args is None:
        args = {}
    if not isinstance(args, dict):
        raise ToolArgError("arguments must be an object / arguments 必須是物件")
    schema = TOOL_SPECS[name]["inputSchema"]
    props = schema.get("properties") or {}
    for key in schema.get("required") or []:
        if key not in args:
            raise ToolArgError(f"missing required argument: {key} / 缺少必要參數：{key}")
    clean: dict = {}
    for key, val in args.items():
        if key not in props:
            raise ToolArgError(f"unknown argument: {key} / 不認得的參數：{key}")
        p = props[key]
        want = _TYPES[p["type"]]
        if want is int and isinstance(val, str) and val.strip().lstrip("-").isdigit():
            val = int(val)
        if not isinstance(val, want) or (want is int and isinstance(val, bool)):
            raise ToolArgError(f"argument {key} must be {p['type']} / 參數 {key} 型別應為 {p['type']}")
        if "enum" in p and val not in p["enum"]:
            raise ToolArgError(f"argument {key} must be one of {p['enum']} / 參數 {key} 不在允許值內")
        if want is int:
            val = max(p.get("minimum", val), min(p.get("maximum", val), val))
        if want is str and len(val) > MAX_TEXT:
            raise ToolArgError(f"argument {key} too long / 參數 {key} 過長")
        clean[key] = val
    return clean


def boot() -> None:
    yhbmail.init_db()
    if (yhbmail.load_cfg().get("mode") or "demo") == "demo":
        yhbmail.seed_demo()


def _error(id_, code: int, message: str, data=None) -> dict:
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": err}


def _result(id_, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def call_tool(params: dict) -> dict:
    name = params.get("name")
    if not isinstance(name, str) or name not in TOOL_SPECS:
        raise LookupError(name)
    try:
        args = validate_args(name, params.get("arguments"))
    except ToolArgError as e:
        return {"content": [{"type": "text", "text": str(e)}], "isError": True}
    try:
        payload = agent_bridge.invoke_tool(name, args)
    except Exception as e:  # tool failure is a result, not a protocol error
        print(traceback.format_exc(), file=sys.stderr)
        return {"content": [{"type": "text", "text": f"tool {name} failed / 工具執行失敗：{str(e)[:300]}"}],
                "isError": True}
    if name == "save_draft":
        payload = {**payload, "sent": False}
    text = json.dumps(payload, ensure_ascii=False, default=str)
    return {"content": [{"type": "text", "text": text}],
            "structuredContent": payload if isinstance(payload, dict) else {"result": payload},
            "isError": False}


def handle(msg) -> dict | None:
    """Handle one JSON-RPC message. Returns a response, or None for notifications."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
        rid = msg.get("id") if isinstance(msg, dict) else None
        if isinstance(msg, dict) and "method" not in msg and ("result" in msg or "error" in msg):
            return None  # a response to something we never asked; ignore
        return _error(rid, INVALID_REQUEST, "Invalid Request")
    method = msg["method"]
    is_note = "id" not in msg
    rid = msg.get("id")
    params = msg.get("params") or {}
    if is_note:
        return None
    if not isinstance(params, dict):
        return _error(rid, INVALID_PARAMS, "params must be an object")
    try:
        if method == "initialize":
            asked = params.get("protocolVersion")
            version = asked if asked in SUPPORTED_VERSIONS else LATEST_VERSION
            return _result(rid, {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "title": "TooPowerInbox", "version": SERVER_VERSION},
                "instructions": INSTRUCTIONS,
            })
        if method == "ping":
            return _result(rid, {})
        if method == "tools/list":
            return _result(rid, {"tools": mcp_tools()})
        if method == "tools/call":
            try:
                return _result(rid, call_tool(params))
            except LookupError as e:
                return _error(rid, INVALID_PARAMS, f"Unknown tool: {e.args[0] if e.args else ''}")
        return _error(rid, METHOD_NOT_FOUND, f"Method not found: {method}")
    except Exception as e:
        print(traceback.format_exc(), file=sys.stderr)
        return _error(rid, INTERNAL_ERROR, "Internal error", str(e)[:300])


def handle_line(line: str):
    line = line.strip()
    if not line:
        return None
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        return _error(None, PARSE_ERROR, "Parse error")
    if isinstance(msg, list):
        if not msg:
            return _error(None, INVALID_REQUEST, "Invalid Request")
        out = [r for r in (handle(m) for m in msg) if r is not None]
        return out or None
    return handle(msg)


def serve(stdin=None, stdout=None) -> None:
    stdin = stdin or io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="replace")
    stdout = stdout or io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", write_through=True)
    sys.stdout = sys.stderr  # stray prints must never corrupt the protocol stream
    for line in stdin:
        resp = handle_line(line)
        if resp is None:
            continue
        stdout.write(json.dumps(resp, ensure_ascii=False, default=str) + "\n")
        stdout.flush()


def main() -> None:
    boot()
    print(f"{SERVER_NAME} MCP server ready (stdio) root={yhbmail.ROOT}", file=sys.stderr, flush=True)
    try:
        serve()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
