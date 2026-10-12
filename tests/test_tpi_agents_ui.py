"""F32 F33 UI and repo-rule checks: the agents module loads, is bilingual, previews cards safely,
and the feature files obey the hard rules (no send path, no hosting config, stdlib only)."""
from __future__ import annotations

import ast
import re
import shutil
import subprocess
import unittest

import _tpi_server as srv

MODULE = srv.REPO / "ui" / "modules" / "agents.js"
FEATURE = srv.REPO / "server" / "features" / "agents.py"
TEST_FILES = sorted(srv.REPO.glob("tests/test_tpi_agents_*.py"))


class UiModuleTest(unittest.TestCase):
    def test_module_is_served_through_the_loader(self):
        status, body = srv.call("GET", "/api/ui-modules")
        self.assertEqual(status, 200)
        self.assertIn("/ui/modules/agents.js", body["modules"])
        s, headers, raw = srv.request("GET", "/ui/modules/agents.js")
        self.assertEqual(s, 200)
        self.assertIn("javascript", headers["Content-Type"])

    def test_module_has_chinese_and_english_strings(self):
        src = MODULE.read_text()
        self.assertIn("zh: {", src)
        self.assertIn("en: {", src)
        for key in ("nav", "title", "mentionTitle", "person", "company", "meeting", "openHtml"):
            self.assertRegex(src, rf"\b{key}:")

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_module_parses(self):
        r = subprocess.run(["node", "--check", str(MODULE)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)

    def test_html_preview_is_sandboxed_without_scripts(self):
        src = MODULE.read_text()
        self.assertIn('sandbox=""', src, "the HTML card preview is an iframe with the most restrictive sandbox")
        self.assertNotIn("allow-scripts", src)
        self.assertNotIn("allow-same-origin", src)

    def test_module_only_calls_local_agent_endpoints(self):
        src = MODULE.read_text()
        calls = set(re.findall(r'"(/api/[^"?]+)', src))
        self.assertTrue(calls)
        for path in calls:
            self.assertTrue(path.startswith("/api/agents/"), path)

    def test_nav_entry_and_no_core_edits_needed(self):
        self.assertIn('dataset.view = "agents"', MODULE.read_text())


class RepoRulesTest(unittest.TestCase):
    """Hard rules from the task brief, checked against this feature's own files."""

    # Words are assembled from fragments so this file never contains them literally.
    FORBIDDEN_SEND = ("smtp" + "lib", "send" + "mail", "send_" + "mail", "send_" + "message", "Send" + "Email")
    FORBIDDEN_HOST = ("wrang" + "ler", "ver" + "cel", "net" + "lify", "fly" + ".toml", "Proc" + "file")
    FORBIDDEN_WORKFLOW = ("de" + "ploy", "pub" + "lish", "rel" + "ease")

    def _files(self):
        return [FEATURE, MODULE, *TEST_FILES]

    def test_no_send_path_in_feature_code(self):
        for p in self._files():
            text = p.read_text()
            for word in self.FORBIDDEN_SEND:
                self.assertNotIn(word, text, f"{p.name} contains {word}")

    def test_no_hosting_config_in_feature_code(self):
        for p in self._files():
            text = p.read_text().lower()
            for word in self.FORBIDDEN_HOST:
                self.assertNotIn(word.lower(), text, f"{p.name} contains {word}")

    def test_no_deploy_or_publish_words_in_workflows(self):
        for wf in (srv.REPO / ".github" / "workflows").glob("*.yml"):
            text = wf.read_text().lower()
            for word in self.FORBIDDEN_WORKFLOW:
                self.assertNotIn(word, text, f"{wf.name} contains {word}")

    def test_feature_uses_only_stdlib(self):
        tree = ast.parse(FEATURE.read_text())
        stdlib_ok = {"__future__", "html", "json", "re", "datetime", "pathlib", "features", "yhbmail",
                     "agent_bridge", "persona", "os"}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    self.assertIn(a.name.split(".")[0], stdlib_ok, a.name)
            elif isinstance(node, ast.ImportFrom):
                self.assertIn((node.module or "").split(".")[0], stdlib_ok, node.module)

    def test_example_addresses_only(self):
        for p in self._files():
            text = p.read_text()
            for addr in re.findall(r"[\w.+-]+@([\w.-]+\.\w+)", text):
                self.assertTrue(
                    addr == "example.com" or addr.endswith(".example.com") or addr.endswith(".example"),
                    f"{p.name} has a non-example address domain: {addr}")

    def test_feature_mounts_through_the_plugin_loader(self):
        # The feature must register via features/ and ui/modules/; app.py only mounts the loader once.
        self.assertIn("agents", srv.features.LOADED)
        app = (srv.REPO / "server" / "app.py").read_text()
        self.assertEqual(app.count("features.mount("), 1)


if __name__ == "__main__":
    unittest.main()
