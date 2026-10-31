"""Fast, offline smoke checks for module imports and the overnight CLI help."""

import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "server"


class ModuleImportSmokeTests(unittest.TestCase):
    def test_python_modules_import(self):
        original_path = list(sys.path)
        sys.path.insert(0, str(SERVER))
        try:
            importlib.import_module("server")
            importlib.import_module("features")

            modules = []
            modules.extend(
                path.stem
                for path in sorted(SERVER.glob("*.py"))
                if path.name != "__init__.py"
            )
            modules.extend(
                "features." + path.stem
                for path in sorted((SERVER / "features").glob("*.py"))
                if path.name != "__init__.py"
            )
            modules.extend(
                [
                    "fmb_feature2",
                    "fmb_feature2.imap_mailbox",
                    "fmb_feature2.feature_imap_mailbox",
                ]
            )

            for module_name in modules:
                with self.subTest(module=module_name):
                    importlib.import_module(module_name)
        finally:
            sys.path[:] = original_path


class OfflineCliSmokeTests(unittest.TestCase):
    def test_overnight_help_works_with_fake_offline_config(self):
        with tempfile.TemporaryDirectory(prefix="openinbox-fmb-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            (temp_root / "accounts.json").write_text(
                json.dumps({"mode": "live", "accounts": [], "calendars": []}),
                encoding="utf-8",
            )
            (temp_root / "agent.json").write_text(
                json.dumps({"driver": "local"}),
                encoding="utf-8",
            )

            env = {
                key: os.environ[key]
                for key in ("PATH", "SYSTEMROOT", "WINDIR", "PATHEXT")
                if key in os.environ
            }
            env.update(
                {
                    "HOME": str(temp_root),
                    "TMPDIR": str(temp_root),
                    "TEMP": str(temp_root),
                    "TMP": str(temp_root),
                    "OPENINBOX_ROOT": str(temp_root),
                    "OPENINBOX_NO_BROWSER": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "PYTHONIOENCODING": "utf-8",
                }
            )

            result = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "overnight.py"), "--help"],
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=15,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("usage", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    unittest.main()
