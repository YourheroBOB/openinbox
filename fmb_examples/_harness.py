"""fmb_examples 共用沙箱與小工具（只用標準函式庫，不連網）。

每個範例都在「這個 repo 的一次性副本」裡跑：真實的 `accounts.json`、`agent.json`、
`rules.json`、`data/`、`vault/`、`*.db` 都不會被複製進去，所以範例不可能讀寫到你真的
信箱快取、草稿或憑證設定。副本缺設定檔時，會從 `*.example.json` 產生
（`mode: demo`、`driver: local`），因此不會有對外連線。

想保留副本檢查內容：`export FMB_EXAMPLE_ROOT=/tmp/fmb-inspect`（此目錄不會被自動刪除）。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "__pycache__", "data", "vault", "node_modules", ".idea", ".vscode", ".pr-review"}
SKIP_FILES = {"accounts.json", "agent.json", "rules.json"}
SKIP_SUFFIXES = (".pyc", ".db", ".db-wal", ".db-shm", ".log")

_temp_root: "Path | None" = None


class Checks:
    """收集檢查結果；`verdict()` 印出 PASS／FAIL／SKIP 並回傳結束碼。"""

    def __init__(self, title: str) -> None:
        self.title = title
        self.failed: list = []
        self.skipped = False

    def check(self, label: str, ok: bool, detail: str = "") -> bool:
        mark = "ok" if ok else "FAIL"
        tail = f" — {_clip(detail)}" if detail else ""
        print(f"   [{mark}] {label}{tail}")
        if not ok:
            self.failed.append(label)
        return bool(ok)

    def info(self, label: str, detail: str = "") -> None:
        tail = f" — {_clip(detail)}" if detail else ""
        print(f"   [info] {label}{tail}")

    def skip(self, reason: str) -> None:
        self.skipped = True
        print(f"   SKIP: {reason}")

    def verdict(self) -> int:
        if self.failed:
            print(f"FAIL: {self.title} — {len(self.failed)} 項未通過：{', '.join(self.failed)}")
            return 1
        if self.skipped:
            print(f"SKIP: {self.title}（模組不在這個 checkout，不算失敗）")
            return 0
        print(f"PASS: {self.title}")
        return 0


def _clip(text: str, limit: int = 200) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _ignore(_dir, names):
    return {
        n
        for n in names
        if n in SKIP_DIRS or n in SKIP_FILES or n.startswith(".env") or n.endswith(SKIP_SUFFIXES)
    }


def _seed(root: Path) -> None:
    for name, example in (("accounts.json", "accounts.example.json"), ("agent.json", "agent.example.json")):
        target = root / name
        if target.exists():
            continue
        src = REPO / example
        if src.is_file():
            shutil.copyfile(src, target)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "vault" / "cards").mkdir(parents=True, exist_ok=True)


def _guard(root: Path) -> Path:
    root = root.resolve()
    if root == REPO or REPO in root.parents:
        raise SystemExit(f"沙箱不能是 repo 本身或 repo 內的目錄：{root}")
    return root


def start() -> Path:
    """建立（或重用 `FMB_EXAMPLE_ROOT`）沙箱，回傳其根目錄。"""
    global _temp_root
    reuse = os.environ.get("FMB_EXAMPLE_ROOT", "").strip()
    if reuse:
        root = Path(reuse).expanduser()
        root.mkdir(parents=True, exist_ok=True)
        root = _guard(root)
        shutil.copytree(REPO, root, ignore=_ignore, dirs_exist_ok=True)
        _seed(root)
        return root
    root = _guard(Path(tempfile.mkdtemp(prefix="fmb-openinbox-")))
    shutil.copytree(REPO, root, ignore=_ignore, dirs_exist_ok=True)
    _seed(root)
    _temp_root = root
    return root


def cleanup() -> None:
    """刪除本次自動建立的沙箱；`FMB_EXAMPLE_ROOT` 指定的目錄不刪。"""
    global _temp_root
    if _temp_root is not None and _temp_root.exists():
        shutil.rmtree(_temp_root, ignore_errors=True)
    _temp_root = None


def child_env(root: Path, **extra) -> dict:
    """給子程序用的環境：指向沙箱、不開瀏覽器、不繼承 proxy 設定。"""
    env = {k: v for k, v in os.environ.items() if not k.lower().endswith("_proxy")}
    env["OPENINBOX_ROOT"] = str(root)
    env["OPENINBOX_NO_BROWSER"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = str(root / "server") + os.pathsep + env.get("PYTHONPATH", "")
    env.pop("OPENINBOX_PORT", None)
    env.update({k: str(v) for k, v in extra.items()})
    return env


def use_root(root: Path) -> None:
    """在 import server/ 模組之前，把這個行程指向沙箱。"""
    os.environ["OPENINBOX_ROOT"] = str(root)
    os.environ.setdefault("OPENINBOX_NO_BROWSER", "1")
    server_dir = str(root / "server")
    if server_dir not in sys.path:
        sys.path.insert(0, server_dir)


def http_get_json(url: str, timeout: float = 5.0):
    """只連 loopback；已關閉 proxy，回傳 (status, payload)。"""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout) as resp:
            return int(resp.status), json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            payload = json.loads(body)
        except ValueError:
            payload = {"error": f"HTTP {e.code}"}
        return int(e.code), payload
