"""Isolated configuration-loading tests.

These tests run the loaders in a subprocess rooted at a temporary directory. They
only use synthetic settings and fake environment values; they never synchronize
mail or invoke an agent.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = REPO_ROOT / "server"

_PROBE = r"""
import json
import agent_bridge
import yhbmail

def observe(loader):
    try:
        return {"ok": True, "value": loader()}
    except Exception as exc:
        # Do not serialize exception messages: they may contain configuration data.
        return {"ok": False, "error": type(exc).__name__}

print(json.dumps({
    "accounts": observe(yhbmail.load_cfg),
    "agent": observe(agent_bridge.load_agent_cfg),
}))
"""


class ConfigSettingsTests(unittest.TestCase):
    def _probe(self, root: Path) -> dict:
        env = {
            "OPENINBOX_ROOT": str(root),
            "PYTHONPATH": str(SERVER_DIR),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PATH": os.environ.get("PATH", ""),
            "FAKE_IMAP_PASSWORD_FOR_TEST": "FAKE_VALUE_FOR_TEST",
            "FAKE_AGENT_KEY_FOR_TEST": "FAKE_VALUE_FOR_TEST",
        }
        result = subprocess.run(
            [sys.executable, "-c", _PROBE],
            cwd=root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            result.returncode,
            0,
            msg="Configuration probe failed without exposing its output.",
        )
        return json.loads(result.stdout)

    def test_missing_settings_use_safe_demo_and_local_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            result = self._probe(Path(temp_dir))

        self.assertTrue(result["accounts"]["ok"])
        self.assertEqual(result["accounts"]["value"].get("mode"), "demo")
        self.assertTrue(result["agent"]["ok"])
        self.assertEqual(result["agent"]["value"].get("driver") or "local", "local")

    def test_temp_settings_and_environment_variable_references_are_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            accounts = {
                "mode": "live",
                "accounts": [
                    {
                        "email": "test@example.invalid",
                        "driver": "imap",
                        "password_env": "FAKE_IMAP_PASSWORD_FOR_TEST",
                    }
                ],
            }
            agent = {
                "driver": "local",
                "openai_compatible": {
                    "api_key_env": "FAKE_AGENT_KEY_FOR_TEST",
                },
            }
            (root / "accounts.json").write_text(
                json.dumps(accounts), encoding="utf-8"
            )
            (root / "agent.json").write_text(json.dumps(agent), encoding="utf-8")

            result = self._probe(root)

        self.assertTrue(result["accounts"]["ok"])
        loaded_accounts = result["accounts"]["value"]
        self.assertEqual(loaded_accounts.get("mode"), "live")
        self.assertEqual(
            loaded_accounts["accounts"][0].get("password_env"),
            "FAKE_IMAP_PASSWORD_FOR_TEST",
        )
        self.assertTrue(result["agent"]["ok"])
        self.assertEqual(result["agent"]["value"].get("driver"), "local")

        # The loaders may retain environment variable names, but must not expose
        # their values in the loaded configuration.
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("FAKE_VALUE_FOR_TEST", serialized)

    def test_malformed_settings_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "accounts.json").write_text("{ invalid", encoding="utf-8")
            (root / "agent.json").write_text("{ invalid", encoding="utf-8")

            result = self._probe(root)

        accounts = result["accounts"]
        if accounts["ok"]:
            self.assertIsInstance(accounts["value"], dict)
            self.assertNotEqual(accounts["value"].get("mode"), "live")

        agent = result["agent"]
        if agent["ok"]:
            self.assertIsInstance(agent["value"], dict)
            self.assertEqual(agent["value"].get("driver") or "local", "local")


if __name__ == "__main__":
    unittest.main()
