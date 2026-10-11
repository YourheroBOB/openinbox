"""Repo guardrails: no outbound-mail code, no deploy config, stdlib only, example data only."""
from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CODE_SUFFIXES = {".py", ".js", ".html", ".sh", ".yml", ".yaml", ".json", ".toml"}
SKIP_DIRS = {".git", "data", "__pycache__", "state"}

# Assembled at runtime so this file does not itself contain the banned words.
BANNED_CODE_WORDS = ["smtp" + "lib", "send" + "mail", "send" + "_mail", "send" + "_message", "Send" + "Email"]
BANNED_WORKFLOW_WORDS = ["de" + "ploy", "pub" + "lish", "re" + "lease"]
DEPLOY_FILES = {"wrangler.toml", "wrangler.json", "wrangler.jsonc", "vercel.json", "netlify.toml",
                "fly.toml", "Procfile"}
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
ALLOWED_EMAIL_DOMAIN = re.compile(r"(^|\.)example(\.(com|org|net))?$", re.I)


def repo_files():
    for dirpath, dirnames, filenames in os.walk(REPO):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            yield Path(dirpath) / name


def tracked_files():
    try:
        out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-co", "--exclude-standard"],
                             check=True, capture_output=True, text=True).stdout
    except (OSError, subprocess.CalledProcessError):
        local_only = {"accounts.json", "agent.json"}
        return [p for p in repo_files() if p.name not in local_only and "vault" not in p.relative_to(REPO).parts]
    return [REPO / rel for rel in out.splitlines() if (REPO / rel).is_file() and not rel.startswith("state/")]


class RepoRulesTest(unittest.TestCase):
    def test_no_outbound_mail_code(self):
        for p in repo_files():
            if p.suffix not in CODE_SUFFIXES:
                continue
            text = p.read_text(errors="replace")
            for word in BANNED_CODE_WORDS:
                self.assertNotIn(word, text, f"{p.relative_to(REPO)} contains {word!r}")

    def test_workflows_have_no_ship_steps(self):
        for p in (REPO / ".github" / "workflows").glob("*.y*ml"):
            text = p.read_text().lower()
            for word in BANNED_WORKFLOW_WORDS:
                self.assertNotIn(word, text, f"{p.name} contains {word!r}")

    def test_no_deploy_config(self):
        found = [str(p.relative_to(REPO)) for p in repo_files() if p.name in DEPLOY_FILES]
        self.assertEqual(found, [])

    def test_only_example_addresses(self):
        for p in tracked_files():
            if p.suffix in {".png", ".jpg", ".ico", ".db"}:
                continue
            for m in EMAIL_RE.finditer(p.read_text(errors="replace")):
                self.assertRegex(m.group(1), ALLOWED_EMAIL_DOMAIN,
                                 f"{p.relative_to(REPO)} has a non-example address")

    @unittest.skipUnless(hasattr(sys, "stdlib_module_names"), "needs Python 3.10+")
    def test_python_is_stdlib_only(self):
        local = {p.stem for p in (REPO / "server").glob("*.py")} | {"features", "server"}
        local |= {p.stem for p in (REPO / "tests").glob("*.py")}
        for p in list((REPO / "server").rglob("*.py")) + list((REPO / "tests").glob("*.py")):
            tree = ast.parse(p.read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                else:
                    continue
                for name in names:
                    top = name.split(".")[0]
                    self.assertTrue(top in sys.stdlib_module_names or top in local or top == "__future__",
                                    f"{p.relative_to(REPO)} imports non-stdlib {name}")

    def test_server_binds_loopback_only(self):
        src = (REPO / "server" / "app.py").read_text()
        self.assertIn('ThreadingHTTPServer(("127.0.0.1", PORT)', src)
        self.assertNotIn("0.0.0.0", src)


class SmokeWiringTest(unittest.TestCase):
    def test_workflow_runs_unittest(self):
        text = (REPO / ".github" / "workflows" / "smoke.yml").read_text()
        self.assertIn("run: python3 -m unittest discover -s tests", text)

    def test_smoke_script(self):
        script = REPO / "scripts" / "smoke.sh"
        self.assertTrue(script.is_file())
        self.assertTrue(os.access(script, os.X_OK), "scripts/smoke.sh must be executable")
        self.assertIn("smoke.yml", script.read_text())
        r = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)


class ReadmeTest(unittest.TestCase):
    def test_cloud_linux_section_both_languages(self):
        for name, heading in (("README.md", "## Run on a cloud Linux host"),
                              ("README.zh-Hant.md", "## 在雲端 Linux 主機執行")):
            text = (REPO / name).read_text()
            self.assertIn(heading, text, name)
            section = text.split(heading, 1)[1].split("\n## ", 1)[0]
            self.assertIn("ssh -N -L 8770:127.0.0.1:8770", section, name)
            self.assertIn("OPENINBOX_NO_BROWSER=1 ./run.sh", section, name)
            self.assertNotIn("0.0.0.0", section, name)


if __name__ == "__main__":
    unittest.main()
