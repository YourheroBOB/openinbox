"""Isolated tests for configuration loading, defaults, and malformed files.

All settings are created under temporary directories. The child process receives a
minimal environment, so it cannot read the developer's settings or credentials.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


class ConfigLoadingTests(unittest.TestCase):
    def _load(self, root, module, function):
        env = {
            "OPENINBOX_ROOT": str(root),
            "PYTHONPATH": str(REPO_ROOT / "server"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(root),
            "TMPDIR": str(root),
        }
        if os.name == "nt":
            for name in ("PATH", "SYSTEMROOT", "WINDIR"):
                if name in os.environ:
                    env[name] = os.environ[name]
        else:
            env["PATH"] = os.environ.get("PATH", os.defpath)

        code = (
            "import json\n"
            f"import {module}\n"
            "try:\n"
            f"    value = {module}.{function}()\n"
            "except Exception as exc:\n"
            "    print(json.dumps({'error_type': type(exc).__name__}))\n"
            "else:\n"
            "    print(json.dumps({'value': value}))\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=REPO_ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        output_lines = result.stdout.strip().splitlines()
        self.assertTrue(output_lines, msg="Configuration loader produced no result")
        return json.loads(output_lines[-1])

    def test_accounts_config_is_loaded_from_openinbox_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = {
                "mode": "demo",
                "accounts": [
                    {
                        "email": "config-test@example.invalid",
                        "platform": "gmail",
                        "driver": "demo",
                        "label": "FAKE_VALUE_FOR_TEST",
                    }
                ],
            }
            (root / "accounts.json").write_text(
                json.dumps(config), encoding="utf-8"
            )

            result = self._load(root, "yhbmail", "load_cfg")

        self.assertIn("value", result)
        self.assertEqual(result["value"]["mode"], "demo")
        self.assertEqual(
            result["value"]["accounts"][0]["label"], "FAKE_VALUE_FOR_TEST"
        )

    def test_agent_config_is_loaded_from_openinbox_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = {
                "driver": "cli",
                "cli": {
                    "command": ["FAKE_VALUE_FOR_TEST"],
                    "timeout_sec": 1,
                },
            }
            (root / "agent.json").write_text(
                json.dumps(config), encoding="utf-8"
            )

            result = self._load(root, "agent_bridge", "load_agent_cfg")

        self.assertIn("value", result)
        self.assertEqual(result["value"]["driver"], "cli")
        self.assertEqual(
            result["value"]["cli"]["command"], ["FAKE_VALUE_FOR_TEST"]
        )

    def test_missing_configs_use_safe_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            accounts = self._load(root, "yhbmail", "load_cfg")
            agent = self._load(root, "agent_bridge", "load_agent_cfg")

        self.assertIn("value", accounts)
        self.assertEqual(accounts["value"]["mode"], "demo")
        self.assertIsInstance(accounts["value"].get("accounts"), list)
        self.assertIn("value", agent)
        self.assertEqual(agent["value"]["driver"], "local")

    def test_malformed_configs_fail_clearly_or_return_safe_mappings(self):
        malformed = "{ FAKE_VALUE_FOR_TEST"

        for module, function, filename in (
            ("yhbmail", "load_cfg", "accounts.json"),
            ("agent_bridge", "load_agent_cfg", "agent.json"),
        ):
            with self.subTest(filename=filename):
                with tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    (root / filename).write_text(malformed, encoding="utf-8")
                    result = self._load(root, module, function)

                if "error_type" in result:
                    self.assertIn(
                        result["error_type"], {"JSONDecodeError", "ValueError"}
                    )
                else:
                    self.assertIsInstance(result.get("value"), dict)
                    self.assertNotEqual(result["value"], malformed)


if __name__ == "__main__":
    unittest.main()
