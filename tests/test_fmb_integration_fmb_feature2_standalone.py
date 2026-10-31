"""Isolation checks for the optional fmb_feature2 add-on modules.

The documented contract of fmb_feature2 is that its modules are self-contained:
they import cleanly on their own, and `feature_imap_mailbox.py` must NOT bind
any HTTP route when it lives outside server/features/. Each check runs in a
clean subprocess (PYTHONPATH pinned to the repo root) so that state leaked by
other tests in the same interpreter -- for example a `features` package made
importable by another test module -- cannot affect the result.

No network, no pip, stdlib only, no credential-shaped values.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_py(code: str, timeout: int = 60):
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO)  # deterministic: exactly the repo root
    return subprocess.run([sys.executable, "-c", code], cwd=str(REPO),
                          capture_output=True, text=True, env=env, timeout=timeout)


class FmbFeature2Standalone(unittest.TestCase):

    def _assert_ok(self, r, code):
        self.assertEqual(r.returncode, 0,
                         "subprocess check failed\ncode:\n%s\nstdout:\n%s\nstderr:\n%s"
                         % (code, r.stdout, r.stderr))

    @unittest.skipIf(not (REPO / "fmb_feature2" / "__init__.py").is_file(),
                     "fmb_feature2 package not present")
    def test_package_imports_standalone(self):
        code = "import fmb_feature2\nprint('ok')\n"
        r = run_py(code)
        self._assert_ok(r, code)
        self.assertIn("ok", r.stdout)

    @unittest.skipIf(not (REPO / "fmb_feature2" / "imap_mailbox.py").is_file(),
                     "fmb_feature2/imap_mailbox.py not present")
    def test_imap_mailbox_imports_standalone(self):
        code = "import fmb_feature2.imap_mailbox\nprint('ok')\n"
        r = run_py(code)
        self._assert_ok(r, code)
        self.assertIn("ok", r.stdout)

    @unittest.skipIf(not (REPO / "fmb_feature2" / "feature_imap_mailbox.py").is_file(),
                     "fmb_feature2/feature_imap_mailbox.py not present")
    def test_feature_glue_stays_unwired_outside_server_features(self):
        code = (
            "import fmb_feature2.feature_imap_mailbox as m\n"
            "assert m.get is None, 'route decorator bound outside server/features/'\n"
            "assert m.audit_accounts is None, 'audit_accounts resolved outside server/features/'\n"
            "print('ok')\n"
        )
        r = run_py(code)
        self._assert_ok(r, code)
        self.assertIn("ok", r.stdout)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
