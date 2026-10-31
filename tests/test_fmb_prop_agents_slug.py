"""Invariant tests for the local deliverable slug helper."""
import os
from pathlib import Path
import re
import sys
import tempfile
import unittest


# Keep module initialization isolated from any local Openinbox data.
_IMPORT_ROOT = tempfile.TemporaryDirectory(prefix="openinbox-fmb-prop-")
_SERVER_DIR = str(Path(__file__).resolve().parents[1] / "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

_previous_root = os.environ.get("OPENINBOX_ROOT")
os.environ["OPENINBOX_ROOT"] = _IMPORT_ROOT.name
try:
    from features.agents import _slug
finally:
    if _previous_root is None:
        os.environ.pop("OPENINBOX_ROOT", None)
    else:
        os.environ["OPENINBOX_ROOT"] = _previous_root


class SlugInvariantTests(unittest.TestCase):
    def test_slug_is_safe_bounded_and_idempotent(self):
        corpus = [
            "",
            "   ",
            "A",
            "Alpha__Beta",
            "a/b\\c",
            "punctuation !? and spaces",
            "é",
            "郵件主旨",
            "x" * 100,
            "A!" * 60,
        ]
        # Exercise every ASCII character as a separator as well as punctuation
        # runs, without relying on a third-party property-testing package.
        corpus.extend("left" + chr(codepoint) + "right" for codepoint in range(128))

        safe_slug = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        for value in corpus:
            with self.subTest(value=repr(value)):
                result = _slug(value)
                self.assertRegex(result, safe_slug)
                self.assertLessEqual(len(result), 40)
                self.assertEqual(_slug(result), result)

    def test_slug_normalizes_case_and_separator_runs(self):
        expected = "alpha-beta"
        for value in ("Alpha__Beta", "alpha / beta", "ALPHA...BETA"):
            with self.subTest(value=value):
                self.assertEqual(_slug(value), expected)

    def test_slug_preserves_the_truncation_boundary(self):
        result = _slug("A" * 100)
        self.assertEqual(len(result), 40)
        self.assertEqual(result, "a" * 40)


if __name__ == "__main__":
    unittest.main()
