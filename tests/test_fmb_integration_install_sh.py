"""End-to-end tests for install.sh (CLI execution + file I/O + error paths).

The real bash script is run inside a throwaway staging directory that contains
only install.sh and the two example config files, exactly like a fresh clone.
The operator's real checkout (accounts.json, agent.json, data/, vault/) is never
touched. No network, no pip. The only fake marker used is the literal string
FAKE_VALUE_FOR_TEST; no credential-shaped value ever appears.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASH = shutil.which("bash")
FAKE = "FAKE_VALUE_FOR_TEST"
NEEDED = ("install.sh", "accounts.example.json", "agent.example.json")


def _stage_copy(base: Path) -> Path:
    stage = base / "stage"
    stage.mkdir()
    for name in NEEDED:
        shutil.copy(REPO / name, stage / name)
    return stage


def _run_install(stage: Path, env_overrides=None):
    env = dict(os.environ)
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run([BASH, "install.sh"], cwd=str(stage),
                          capture_output=True, text=True, timeout=120, env=env)


@unittest.skipIf(BASH is None, "bash not available")
@unittest.skipIf(not all((REPO / n).is_file() for n in NEEDED),
                 "install.sh or example configs not present")
class InstallScriptEndToEnd(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="fmb_install_")
        self.tmp = Path(self._tmp.name)
        self.stage = _stage_copy(self.tmp)

    def tearDown(self):
        self._tmp.cleanup()

    def _assert_ok(self, r):
        self.assertEqual(r.returncode, 0,
                         "install.sh failed\nstdout:\n%s\nstderr:\n%s" % (r.stdout, r.stderr))

    def test_fresh_install_creates_layout_and_demo_defaults(self):
        r = _run_install(self.stage)
        self._assert_ok(r)
        self.assertTrue((self.stage / "data").is_dir(), "data/ was not created")
        self.assertTrue((self.stage / "vault" / "cards").is_dir(), "vault/cards/ was not created")
        cfg = json.loads((self.stage / "accounts.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg.get("mode"), "demo", "fresh install should default to demo mode")
        agent = json.loads((self.stage / "agent.json").read_text(encoding="utf-8"))
        self.assertEqual(agent.get("driver"), "local", "fresh agent.json should use the local driver")

    def test_reinstall_preserves_user_edits(self):
        self._assert_ok(_run_install(self.stage))
        accounts = self.stage / "accounts.json"
        agent = self.stage / "agent.json"
        cfg = json.loads(accounts.read_text(encoding="utf-8"))
        cfg["fmb_marker"] = FAKE
        accounts.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        ag = json.loads(agent.read_text(encoding="utf-8"))
        ag["fmb_marker"] = FAKE
        agent.write_text(json.dumps(ag, ensure_ascii=False, indent=2), encoding="utf-8")

        r = _run_install(self.stage)
        self._assert_ok(r)
        cfg2 = json.loads(accounts.read_text(encoding="utf-8"))
        self.assertEqual(cfg2.get("fmb_marker"), FAKE,
                         "reinstall must not overwrite the user's accounts.json")
        ag2 = json.loads(agent.read_text(encoding="utf-8"))
        self.assertEqual(ag2.get("fmb_marker"), FAKE,
                         "reinstall must not overwrite the user's agent.json")

    def test_old_python_is_rejected_before_any_file_is_written(self):
        fakebin = self.tmp / "fakebin"
        fakebin.mkdir()
        fake = fakebin / "python3"
        # Emulates a python older than 3.9: it exits non-zero with the message
        # the real check would print, without touching anything else.
        fake.write_text("#!/bin/sh\ncat >/dev/null\necho 'Need python3 3.9+' >&2\nexit 1\n",
                        encoding="utf-8")
        fake.chmod(0o755)
        r = _run_install(self.stage, {"PATH": os.pathsep.join([str(fakebin),
                                                               os.environ.get("PATH", "")])})
        self.assertNotEqual(r.returncode, 0, "install.sh must fail on an old python3")
        self.assertIn("3.9", r.stdout + r.stderr)
        self.assertFalse((self.stage / "accounts.json").exists(),
                         "no config may be written when the python check fails")
        self.assertFalse((self.stage / "data").exists(),
                         "no directory may be created when the python check fails")

    def test_missing_python3_is_rejected(self):
        emptybin = self.tmp / "emptybin"
        emptybin.mkdir()
        r = _run_install(self.stage, {"PATH": str(emptybin)})
        self.assertNotEqual(r.returncode, 0, "install.sh must fail without python3")
        self.assertIn("python3", r.stdout + r.stderr)
        self.assertFalse((self.stage / "accounts.json").exists(),
                         "no config may be written when python3 is missing")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
