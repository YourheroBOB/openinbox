"""Offline smoke test: import the repository's Python modules in an isolated process."""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PythonModuleImportSmokeTest(unittest.TestCase):
    def test_python_modules_import_with_offline_fake_config(self):
        with tempfile.TemporaryDirectory(prefix="openinbox-smoke-") as temp_dir:
            temp_root = Path(temp_dir)
            (temp_root / "accounts.json").write_text(
                json.dumps({"mode": "demo", "accounts": [], "calendars": []}),
                encoding="utf-8",
            )
            (temp_root / "agent.json").write_text(
                json.dumps({"driver": "local"}),
                encoding="utf-8",
            )

            import_script = r"""
import importlib
from pathlib import Path
import sys

root = Path(sys.argv[1])
server = root / "server"
sys.path[:0] = [str(root), str(server)]
modules = []

for path in sorted(server.glob("*.py")):
    name = "server" if path.stem == "__init__" else path.stem
    importlib.import_module(name)
    modules.append(name)

for path in sorted((server / "features").glob("*.py")):
    name = "features" if path.stem == "__init__" else f"features.{path.stem}"
    importlib.import_module(name)
    modules.append(name)

for package_dir in (root / "fmb_feature2",):
    for path in sorted(package_dir.glob("*.py")):
        name = package_dir.name if path.stem == "__init__" else f"{package_dir.name}.{path.stem}"
        importlib.import_module(name)
        modules.append(name)

scripts_dir = root / "scripts"
for path in sorted(scripts_dir.glob("*.py")):
    if path.stem != "__init__":
        name = f"scripts.{path.stem}"
        importlib.import_module(name)
        modules.append(name)

print(f"Imported {len(modules)} Python modules")
"""

            env = {
                "PATH": os.environ.get("PATH", ""),
                "HOME": str(temp_root),
                "USERPROFILE": str(temp_root),
                "OPENINBOX_ROOT": str(temp_root),
                "OPENINBOX_PORT": "0",
                "OPENINBOX_NO_BROWSER": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            if "SYSTEMROOT" in os.environ:
                env["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

            result = subprocess.run(
                [sys.executable, "-c", import_script, str(ROOT)],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=f"Module import smoke failed:\n{result.stderr or result.stdout}",
            )
            self.assertIn("Imported ", result.stdout)


if __name__ == "__main__":
    unittest.main()
