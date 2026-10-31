#!/usr/bin/env python3
"""openinbox（TooPowerInbox）五個離線可執行的使用範例。

跑全部：        python3 fmb_examples/examples.py
只跑一個：      python3 fmb_examples/examples.py 03
指定多個：      python3 fmb_examples/examples.py 01 04

不需要網路、真信箱、模型或金鑰；全部動作都在 repo 的一次性副本裡（見 `_harness.py`）。
輸出只印狀態碼、鍵名、數量與型別，不印信件主旨、寄件人或內文。
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _harness as h  # noqa: E402

EXAMPLES = {
    "01": ("mcp_stdio_smoke", "MCP over stdio：initialize / tools/list / tools/call / ping"),
    "02": ("mention_router", "thread 訊息裡的 @agent 提及 -> 任務（純函式，不碰資料庫）"),
    "03": ("deliverable_card", "成果卡片：Markdown + 轉義過的 HTML，路徑穿越被拒"),
    "04": ("http_inbox_counts", "本機 HTTP API：只印狀態碼、鍵名與數量"),
    "05": ("imap_preflight", "IMAP 設定離線預檢（全假設定，不登入）"),
}


# ── 01 MCP over stdio ────────────────────────────────────────────────────────

def _mcp_text(msg) -> str:
    result = (msg or {}).get("result") or {}
    chunks = []
    for c in result.get("content") or []:
        if isinstance(c, dict) and isinstance(c.get("text"), str):
            chunks.append(c["text"])
    return "\n".join(chunks)


def ex01(root: Path, checks: h.Checks) -> None:
    script = root / "server" / "mcp_server.py"
    if not script.is_file():
        checks.skip("server/mcp_server.py 不在這個 checkout")
        return
    reqs = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize",
         "params": {"protocolVersion": "2025-06-18", "capabilities": {}}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_inbox", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "persona", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 5, "method": "ping"},
        {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "no_such_tool", "arguments": {}}},
    ]
    stdin_text = "\n".join(json.dumps(r, ensure_ascii=False) for r in reqs) + "\n"
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=stdin_text, text=True, encoding="utf-8",
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd=str(root), env=h.child_env(root), timeout=180,
    )
    replies = {}
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(msg, dict) and "id" in msg:
            replies[msg["id"]] = msg
    if not replies:
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        checks.info("server stderr 尾端", " | ".join(tail) or "(空)")

    init = (replies.get(1) or {}).get("result") or {}
    checks.check("1. initialize", bool(init.get("protocolVersion")),
                 f"protocolVersion={init.get('protocolVersion')!r}")

    tools = ((replies.get(2) or {}).get("result") or {}).get("tools") or []
    names = [t.get("name") for t in tools if isinstance(t, dict)]
    want = {"list_inbox", "brain_board", "search_brain", "persona", "save_draft"}
    checks.check("2. tools/list", want.issubset(set(names)),
                 f"{len(names)} tool(s): {', '.join(n for n in names if n)}")

    inbox = _mcp_text(replies.get(3))
    checks.check("3. tools/call list_inbox（唯讀）", bool(inbox), f"{len(inbox)} chars（內容不列印）")
    persona = _mcp_text(replies.get(4))
    checks.check("4. tools/call persona（唯讀）", bool(persona), f"{len(persona)} chars")

    checks.check("5. ping", bool(replies.get(5)), "")
    unknown = replies.get(6) or {}
    handled = bool(unknown.get("error")) or bool((unknown.get("result") or {}).get("isError"))
    checks.check("6. 未知工具被擋下且伺服器不崩潰", handled and proc.returncode == 0,
                 f"exit={proc.returncode}")


# ── 02 @agent 提及 -> 任務 ───────────────────────────────────────────────────

def ex02(root: Path, checks: h.Checks) -> None:
    h.use_root(root)
    try:
        from features.agents import error_label, parse_mention
    except Exception as e:  # noqa: BLE001
        checks.skip(f"server/features/agents.py 無法匯入（{type(e).__name__}）")
        return

    cases = [
        ("@research Samira Ortiz 上週的往來重點", "research_person"),
        ("@agent 幫我準備 Northwind partner office hours 的會議", "meeting_prep"),
        ("@agent Acme Corp 最近動態", "research_company"),
        ("@research-company Byte Cloud 的合約狀況", "research_company"),
        ("@agent Pat Example", "research_person"),
        ("@agent", "research_person"),
    ]
    for i, (text, want) in enumerate(cases, 1):
        parsed = parse_mention(text)
        got = (parsed or {}).get("kind")
        checks.check(f"{i}. {text[:34]}", got == want,
                     f"kind={got} target={(parsed or {}).get('target')!r}")

    checks.check("7. 一般訊息不觸發（triggered=False）",
                 parse_mention("會議前先看這封信") is None)

    class FakeHTTPError(Exception):
        code = 503

    class FakeRemoteError(Exception):
        pass

    checks.check("8. error_label 保留 HTTP 狀態碼",
                 error_label(FakeHTTPError("boom")) == "FakeHTTPError: HTTP 503",
                 error_label(FakeHTTPError("boom")))
    checks.check("9. error_label 從訊息抓到狀態碼但丟掉本文",
                 error_label(FakeRemoteError("upstream said HTTP 429 Too Many Requests")) == "FakeRemoteError: HTTP 429",
                 error_label(FakeRemoteError("upstream said HTTP 429 Too Many Requests")))
    checks.check("10. error_label 只留例外類型",
                 error_label(ConnectionError("FAKE_VALUE_FOR_TEST")) == "ConnectionError",
                 error_label(ConnectionError("FAKE_VALUE_FOR_TEST")))


# ── 03 成果卡片 ─────────────────────────────────────────────────────────────

def ex03(root: Path, checks: h.Checks) -> None:
    h.use_root(root)
    try:
        from features import agents
    except Exception as e:  # noqa: BLE001
        checks.skip(f"server/features/agents.py 無法匯入（{type(e).__name__}）")
        return

    checks.check("成果卡片目錄落在沙箱內",
                 str(Path(agents.DELIV_DIR).resolve()).startswith(str(root)),
                 str(agents.DELIV_DIR))

    body = "\n".join([
        "## 會議準備（示範）",
        "- 目的：對齊 onboarding 範圍",
        "- 與會者：Pat Example",
        "- 需要決定的事：[待填]",
        "",
        "HTML 轉義檢查：<script>alert('FAKE_VALUE_FOR_TEST')</script>",
        "這張卡片沒有任何外部資源或遠端連結。",
    ])
    result = {
        "kind": "meeting_prep", "target": "Pat Example", "text": body,
        "driver": "local", "fallback": True,
        "sources": [{"id": "demo:you@example.com:1", "subject": "（示範信件）",
                     "from": "pat@example.com", "date": "2026-09-16 09:00",
                     "snippet": "（示範片段）"}],
    }
    card = agents.save_deliverable(result, lang="zh-Hant")
    did = card["id"]
    checks.check("save_deliverable 產生合法 id", bool(agents.ID_RE.match(did)), did)

    ids = [c.get("id") for c in agents.list_deliverables(50)]
    checks.check("list_deliverables 看得到新卡片", did in ids, f"{len(ids)} card(s)")

    md = agents.read_deliverable(did, "md")
    checks.check("讀回 .md", md is not None and md[1].startswith("text/markdown"),
                 md[1] if md else "None")
    md_text = md[0].decode("utf-8") if md else ""
    checks.check("md 以卡片標題開頭", md_text.startswith("# "),
                 md_text.splitlines()[0][:60] if md_text else "")
    checks.check("md 保留對象", "Pat Example" in md_text)

    page = agents.read_deliverable(did, "html")
    checks.check("讀回 .html", page is not None and page[1].startswith("text/html"),
                 page[1] if page else "None")
    html_text = page[0].decode("utf-8") if page else ""
    checks.check("HTML 轉義 script", "<script>" not in html_text.lower() and "&lt;script&gt;" in html_text)
    checks.check("HTML 無遠端資源",
                 not any(x in html_text.lower() for x in ("http://", "https://", "src=", "<iframe")))

    checks.check("路徑穿越被拒（../accounts）", agents.read_deliverable("../accounts", "json") is None)
    checks.check("路徑穿越被拒（../../etc/passwd）", agents.read_deliverable("../../etc/passwd", "md") is None)
    checks.check("萬用字元被拒（*）", agents.read_deliverable("*", "json") is None)
    checks.check("不支援的格式被拒（.exe）", agents.read_deliverable(did, "exe") is None)


# ── 04 本機 HTTP API ────────────────────────────────────────────────────────

def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _shape(payload):
    """回傳 (鍵名, 項目數) — 只用來印形狀，不取出任何欄位值。"""
    if isinstance(payload, dict):
        keys = sorted(payload.keys())
        for value in payload.values():
            if isinstance(value, list):
                return keys, len(value)
        return keys, None
    if isinstance(payload, list):
        return [], len(payload)
    return [], None


def _wait_health(base: str, deadline: float = 45.0):
    end = time.time() + deadline
    last = None
    while time.time() < end:
        try:
            status, payload = h.http_get_json(base + "/api/health", timeout=2.0)
            if status == 200 and isinstance(payload, dict):
                return payload
        except (urllib.error.URLError, OSError, ValueError) as e:
            last = e
        time.sleep(0.25)
    print(f"   (最後錯誤：{type(last).__name__ if last else 'timeout'})")
    return None


def _stop(proc) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def ex04(root: Path, checks: h.Checks) -> None:
    app = root / "server" / "app.py"
    if not app.is_file():
        checks.skip("server/app.py 不在這個 checkout")
        return
    port = _free_port()
    log = tempfile.TemporaryFile()
    print(f"   starting server on 127.0.0.1:{port} (loopback only, no browser)")
    proc = subprocess.Popen(
        [sys.executable, str(app)], cwd=str(root),
        env=h.child_env(root, OPENINBOX_PORT=port),
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        health = _wait_health(base)
        if health is None:
            log.seek(0)
            tail = log.read().decode("utf-8", "replace").strip().splitlines()[-5:]
            checks.check("伺服器在 45 秒內啟動", False, " | ".join(tail) or "(無輸出)")
            return
        checks.check("GET /api/health -> 200", True, f"keys={sorted(health.keys())}")
        for path in ("/api/inbox", "/api/providers"):
            try:
                status, payload = h.http_get_json(base + path)
            except (urllib.error.URLError, OSError, ValueError) as e:
                checks.check(f"GET {path}", False, type(e).__name__)
                continue
            keys, count = _shape(payload)
            checks.check(f"GET {path} -> {status}", status == 200, f"items={count} keys={keys}")
    finally:
        _stop(proc)
        log.close()


# ── 05 IMAP 設定預檢 ────────────────────────────────────────────────────────

def ex05(root: Path, checks: h.Checks) -> None:
    feat = root / "fmb_feature2"
    if not (feat / "imap_mailbox.py").is_file():
        checks.skip("fmb_feature2/imap_mailbox.py 不在這個 checkout")
        return
    if str(feat) not in sys.path:
        sys.path.insert(0, str(feat))
    try:
        from imap_mailbox import audit_accounts
    except Exception as e:  # noqa: BLE001
        checks.skip(f"imap_mailbox 無法匯入（{type(e).__name__}）")
        return

    cfg = {
        "mode": "live",
        "accounts": [
            {"email": "you@example.com", "driver": "demo", "label": "Demo inbox"},
            {"email": "me@example.com", "driver": "imap", "provider": "icloud",
             "password_env": "TPI_IMAP_FAKE_PASSWORD", "mailbox": "收件匣"},
            {"email": "work@example.com", "driver": "imap", "host": "imap.example.com",
             "port": 993, "security": "ssl", "mailbox": "Archive/2026"},
        ],
    }
    try:
        report = audit_accounts(cfg)
    except Exception as e:  # noqa: BLE001
        checks.skip(f"audit_accounts 不接受這份假設定（{type(e).__name__}）")
        return

    checks.check("預檢回傳結果（未登入、未連線）", report is not None, f"type={type(report).__name__}")
    raw = json.dumps(report, ensure_ascii=False, default=str)
    checks.check("輸出不超過合理大小（不是整個信箱）", 0 < len(raw) < 200000, f"{len(raw)} chars")
    checks.info("假明文密碼不在設定裡，也不需要任何真實憑證", "password 只以環境變數名稱表示")

    if isinstance(report, dict):
        checks.info("頂層鍵", str(sorted(report.keys())))
        accounts = report.get("accounts")
        if isinstance(accounts, list):
            checks.check("每個帳號都有預檢條目", len(accounts) >= 1, f"{len(accounts)} account(s)")
            for acc in accounts[:3]:
                if not isinstance(acc, dict):
                    continue
                shown = [k for k in ("email", "driver", "mailbox", "wire", "password_env", "warnings")
                         if k in acc]
                checks.info("帳號", f"{acc.get('email', '?')} -> "
                                    + ", ".join(f"{k}={acc[k]!r}"[:60] for k in shown))
        else:
            checks.info("形狀", "回傳 dict 但沒有 accounts 清單，只印鍵名")
    else:
        checks.info("形狀", "回傳不是 dict，只印類型")


# ── 入口 ────────────────────────────────────────────────────────────────────

def _resolve(arg: str):
    a = arg.strip().lower()
    if a in ("all", "*"):
        return "all"
    if a in EXAMPLES:
        return a
    if a.isdigit() and a.zfill(2) in EXAMPLES:
        return a.zfill(2)
    for key, (name, _title) in EXAMPLES.items():
        if a in (name, name.split("_", 1)[-1]):
            return key
    return None


def main(argv) -> int:
    args = [a for a in argv[1:] if a.strip()]
    picked: list = []
    for arg in args or ["all"]:
        key = _resolve(arg)
        if key is None:
            print(f"unknown example: {arg}\navailable: {', '.join(EXAMPLES)} (or 'all')")
            return 2
        if key == "all":
            picked = list(EXAMPLES)
            break
        if key not in picked:
            picked.append(key)

    root = h.start()
    print(f"sandbox: {root}")
    codes = []
    try:
        for key in picked:
            name, title = EXAMPLES[key]
            print(f"\n=== {key} {name} — {title}")
            checks = h.Checks(name)
            fn = globals().get(f"ex{key}")
            if fn is None:
                checks.skip("內部：找不到對應函式")
            else:
                try:
                    fn(root, checks)
                except Exception as e:  # noqa: BLE001
                    checks.check("範例未拋出例外", False, f"{type(e).__name__}: {e}")
            codes.append(checks.verdict())
    finally:
        h.cleanup()

    failed = sum(1 for c in codes if c)
    print("\n" + "=" * 62)
    print(f"summary: {len(codes) - failed}/{len(codes)} example(s) passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
