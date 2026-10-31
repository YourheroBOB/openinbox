"""Regression tests for the agent-failure path in ``server/features/agents.py`` (F32).

The fixed defects these tests hold down:

* ``error_label`` reports only the exception class plus an HTTP status pulled out with a
  strict ``HTTP <3 digits>`` match. It used to surface the exception message, which for
  ``agent_bridge`` can contain the upstream response body or a CLI stderr echo of the
  prompt. A string ``.code`` (or a 4-digit number) must not be read as a status.
* a failing, blank or unknown driver must degrade to the local heuristic with
  ``fallback: true`` and still produce text — never an empty card and never a raised
  exception into the HTTP layer.
* a successful agent answer is kept verbatim (only stripped of surrounding whitespace).
* ``build_pack`` / ``run_task`` reject an unknown task kind before touching any data.
* ``_local_brief`` states plainly when there is no local source, and labels itself as the
  local heuristic; ``_thread_source`` caps the quoted snippet.

No network: the bridge drivers are replaced with local lambdas in every test.
"""
from __future__ import annotations

import atexit
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
_SERVER = ROOT / "server"
if str(_SERVER) not in sys.path:
    sys.path.insert(0, str(_SERVER))

_TMP_ROOT = tempfile.mkdtemp(prefix="fmb-regress-agents-fallback-")
atexit.register(shutil.rmtree, _TMP_ROOT, True)
os.environ.setdefault("OPENINBOX_ROOT", _TMP_ROOT)

try:  # pragma: no cover - import guard only
    from features import agents
except Exception as exc:  # pragma: no cover
    agents = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None

try:  # pragma: no cover - import guard only
    import agent_bridge
except Exception as exc:  # pragma: no cover
    agent_bridge = None
    _BRIDGE_ERROR = exc
else:
    _BRIDGE_ERROR = None


def setUpModule():
    if agents is None:
        raise unittest.SkipTest(f"features.agents unavailable: {_IMPORT_ERROR!r}")
    if agent_bridge is None:
        raise unittest.SkipTest(f"agent_bridge unavailable: {_BRIDGE_ERROR!r}")


class _Boom(Exception):
    """Exception whose message looks like the kind of leak the label must drop."""

    def __init__(self, message, code=None):
        super().__init__(message)
        if code is not None:
            self.code = code


class ErrorLabelTests(unittest.TestCase):
    def test_http_status_is_extracted_without_the_message(self):
        label = agents.error_label(_Boom("upstream said HTTP 500 and echoed the prompt"))
        self.assertEqual(label, "_Boom: HTTP 500")
        self.assertNotIn("prompt", label)

    def test_message_without_a_status_yields_the_class_only(self):
        label = agents.error_label(_Boom("FAKE_VALUE_FOR_TEST leaked into stderr"))
        self.assertEqual(label, "_Boom")
        self.assertNotIn("FAKE_VALUE_FOR_TEST", label)

    def test_four_digit_number_is_not_a_status(self):
        self.assertEqual(agents.error_label(_Boom("HTTP 5000")), "_Boom")

    def test_code_attribute_wins_when_it_is_an_int(self):
        self.assertEqual(agents.error_label(_Boom("HTTP 500", code=429)), "_Boom: HTTP 429")

    def test_string_code_is_ignored(self):
        self.assertEqual(agents.error_label(_Boom("no status here", code="429")), "_Boom")

    def test_builtin_exception_keeps_its_class_name(self):
        self.assertEqual(
            agents.error_label(TimeoutError("HTTP 504 gateway timeout")), "TimeoutError: HTTP 504"
        )


class LocalBriefTests(unittest.TestCase):
    def _pack(self, **kw):
        pack = {
            "task": "research_person",
            "target": "Samira Ortiz",
            "ask": "",
            "lang": "en",
            "persona": None,
            "sources": [],
            "brain": None,
            "rules": [],
        }
        pack.update(kw)
        return pack

    def test_missing_sources_are_stated(self):
        self.assertIn("No matching local data", agents._local_brief(self._pack(lang="en")))
        self.assertIn("本機沒有相關資料", agents._local_brief(self._pack(lang="zh-Hant")))

    def test_each_kind_gets_its_own_section(self):
        self.assertIn("## Meeting prep", agents._local_brief(self._pack(task="meeting_prep", lang="en")))
        self.assertIn(
            "## Company brief", agents._local_brief(self._pack(task="research_company", lang="en"))
        )
        self.assertIn("## Person brief", agents._local_brief(self._pack(lang="en")))
        self.assertIn("## 公司概況", agents._local_brief(self._pack(task="research_company", lang="zh-Hant")))

    def test_sources_are_listed(self):
        pack = self._pack(
            sources=[
                {
                    "id": "e1",
                    "subject": "Weekly sync notes",
                    "from": "samira@example.com",
                    "date": "2026-09-14 09:00",
                    "snippet": "agenda",
                }
            ]
        )
        out = agents._local_brief(pack)
        self.assertIn("Weekly sync notes", out)
        self.assertIn("samira@example.com", out)

    def test_local_heuristic_is_labelled(self):
        self.assertIn("Local heuristic", agents._local_brief(self._pack(lang="en")))
        self.assertIn("本機啟發式", agents._local_brief(self._pack(lang="zh-Hant")))

    def test_missing_target_gets_a_placeholder(self):
        self.assertIn("(no target given)", agents._local_brief(self._pack(target="", lang="en")))

    def test_thread_source_caps_the_quoted_snippet_and_prefers_body_text(self):
        item = {
            "id": "e9",
            "subject": "Re: budget",
            "from_addr": "samira@example.com",
            "date_raw": "2026-09-14 09:00",
            "body_text": "z" * 400,
            "snippet": "short",
        }
        src = agents._thread_source(item)
        self.assertEqual(src["id"], "e9")
        self.assertEqual(len(src["snippet"]), 300)
        self.assertTrue(src["snippet"].startswith("zzz"))

        fallback = agents._thread_source({"id": "e10", "snippet": "only snippet"})
        self.assertEqual(fallback["snippet"], "only snippet")


class UnknownKindTests(unittest.TestCase):
    def test_build_pack_rejects_an_unknown_kind(self):
        with self.assertRaises(ValueError):
            agents.build_pack("not-a-kind", "x")

    def test_run_task_rejects_an_unknown_kind(self):
        with self.assertRaises(ValueError):
            agents.run_task("not-a-kind", "x")


class RunTaskFallbackTests(unittest.TestCase):
    PACK = {
        "task": "research_person",
        "target": "Samira Ortiz",
        "ask": "",
        "lang": "en",
        "persona": None,
        "sources": [],
        "brain": None,
        "rules": [],
    }

    def setUp(self):
        # Capture the real callables first, then stub build_pack so no DB/vault is read.
        self._orig = {
            "build_pack": agents.build_pack,
            "cfg": agent_bridge.load_agent_cfg,
            "openai": agent_bridge._openai,
            "cli": agent_bridge._cli,
            "http": agent_bridge._http,
        }
        agents.build_pack = lambda *a, **k: dict(self.PACK)

    def tearDown(self):
        agents.build_pack = self._orig["build_pack"]
        agent_bridge.load_agent_cfg = self._orig["cfg"]
        agent_bridge._openai = self._orig["openai"]
        agent_bridge._cli = self._orig["cli"]
        agent_bridge._http = self._orig["http"]

    def test_agent_exception_falls_back_and_hides_the_message(self):
        agent_bridge.load_agent_cfg = lambda: {"driver": "openai_compatible"}

        def boom(pack, cfg):
            raise RuntimeError("HTTP 502 upstream body: FAKE_VALUE_FOR_TEST prompt echo")

        agent_bridge._openai = boom
        out = agents.run_task("research_person", "Samira Ortiz", "", "en")
        self.assertTrue(out["fallback"])
        self.assertEqual(out["driver"], "local")
        self.assertEqual(out["error"], "RuntimeError: HTTP 502")
        self.assertIn("Local heuristic", out["text"])
        self.assertNotIn("FAKE_VALUE_FOR_TEST", json.dumps(out, ensure_ascii=False))

    def test_blank_agent_answer_falls_back_to_the_local_brief(self):
        agent_bridge.load_agent_cfg = lambda: {"driver": "cli"}
        agent_bridge._cli = lambda pack, cfg: "   \n"
        out = agents.run_task("research_person", "Samira Ortiz", "", "en")
        self.assertTrue(out["fallback"])
        self.assertEqual(out["driver"], "local")
        self.assertIsNone(out["error"])
        self.assertIn("Local heuristic", out["text"])

    def test_unknown_driver_uses_local_without_an_error(self):
        agent_bridge.load_agent_cfg = lambda: {"driver": "mystery"}
        out = agents.run_task("research_person", "Samira Ortiz", "", "en")
        self.assertEqual(out["driver"], "local")
        self.assertTrue(out["fallback"])
        self.assertIsNone(out["error"])
        self.assertTrue(out["text"].strip())

    def test_agent_answer_is_kept_when_present(self):
        agent_bridge.load_agent_cfg = lambda: {"driver": "http"}
        agent_bridge._http = lambda pack, cfg: "  # Brief\n- one  "
        out = agents.run_task("research_person", "Samira Ortiz", "", "en")
        self.assertEqual(out["driver"], "http")
        self.assertFalse(out["fallback"])
        self.assertIsNone(out["error"])
        self.assertEqual(out["text"], "# Brief\n- one")

    def test_fallback_result_keeps_the_parsed_kind_and_target(self):
        agent_bridge.load_agent_cfg = lambda: {"driver": "cli"}

        def boom(pack, cfg):
            raise OSError("HTTP 503 service unavailable")

        agent_bridge._cli = boom
        out = agents.run_task("research_company", "Northwind Traders", "ask", "en")
        self.assertEqual(out["kind"], "research_company")
        self.assertEqual(out["target"], "Northwind Traders")
        self.assertEqual(out["error"], "OSError: HTTP 503")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
