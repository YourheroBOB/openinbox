"""Repo guardrails for the MCP server: local-only, stdlib-only, documented."""
from __future__ import annotations

import ast
import re
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = REPO / "server" / "mcp_server.py"

BANNED = ["smtp" + "lib", "send" + "mail", "send" + "_mail", "send" + "_message", "Send" + "Email"]
NETWORK_MODULES = {"socket", "ssl", "http", "urllib", "smtp" + "lib", "imaplib", "poplib", "ftplib", "requests"}
LOCAL_MODULES = {"agent_bridge", "yhbmail", "persona", "second_brain"}


def imported_modules(path: Path) -> set[str]:
    mods = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            mods.add(node.module.split(".")[0])
    return mods


class PolicyTest(unittest.TestCase):
    def test_no_send_code_anywhere(self):
        files = [p for p in REPO.rglob("*") if p.is_file() and ".git" not in p.parts
                 and p.suffix in {".py", ".js", ".sh", ".html", ".json", ".yml", ".yaml"}]
        self.assertIn(SERVER, files)
        for p in files:
            text = p.read_text(encoding="utf-8", errors="replace")
            for word in BANNED:
                self.assertNotIn(word, text, f"{word} in {p.relative_to(REPO)}")

    def test_stdlib_only_and_no_network(self):
        mods = imported_modules(SERVER)
        self.assertFalse(mods & NETWORK_MODULES, mods & NETWORK_MODULES)
        stdlib = getattr(sys, "stdlib_module_names", None)
        for m in mods - LOCAL_MODULES - {"__future__"}:
            if stdlib is not None:
                self.assertIn(m, stdlib, m)
        for p in (REPO / "tests").glob("test_tpi_mcp_*.py"):
            third = imported_modules(p) - LOCAL_MODULES - {"__future__"}
            if stdlib is not None:
                self.assertFalse(third - set(stdlib), (p.name, third - set(stdlib)))

    def test_no_deploy_config(self):
        for name in ("wrangler.toml", "wrangler.json", "vercel.json", "netlify.toml", "fly.toml", "Procfile"):
            self.assertFalse((REPO / name).exists(), name)
        for wf in (REPO / ".github" / "workflows").glob("*.y*ml"):
            text = wf.read_text(encoding="utf-8").lower()
            for word in ("deploy", "publish", "release"):
                self.assertNotIn(word, text, f"{word} in {wf.name}")

    def test_readme_documents_mcp_with_placeholders(self):
        for name in ("README.md", "README.zh-Hant.md"):
            text = (REPO / name).read_text(encoding="utf-8")
            self.assertIn("mcp_server.py", text, name)
            self.assertIn('"mcpServers"', text, name)
            self.assertIn("Claude Desktop", text, name)
            self.assertIn("Cursor", text, name)
            self.assertIn("/path/to/openinbox", text, name)
            self.assertNotRegex(text, r"/(Users|home)/[A-Za-z]", name)
        self.assertRegex((REPO / "README.zh-Hant.md").read_text(encoding="utf-8"), r"MCP.*[\u4e00-\u9fff]")

    def test_fixture_mail_uses_example_domains(self):
        text = (REPO / "fixtures" / "demo_inbox.json").read_text(encoding="utf-8")
        for addr in re.findall(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)", text):
            self.assertTrue(addr == "example.com" or addr.endswith(".example") or addr.endswith(".example.com"),
                            addr)


if __name__ == "__main__":
    unittest.main()
