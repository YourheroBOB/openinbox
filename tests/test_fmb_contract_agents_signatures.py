"""Contract tests for the public Agent collaboration module interface.

These tests intentionally focus on stable public signatures and constants rather than
repeating the behavior scenarios covered by the existing tpi-agents tests.
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import features.agents as agents


class AgentPublicInterfaceContractTests(unittest.TestCase):
    def test_public_function_signatures_are_stable(self):
        expected = {
            "parse_mention": (
                ("text", inspect.Parameter.empty),
            ),
            "mentions_alias": (
                ("to_addr", inspect.Parameter.empty),
            ),
            "build_pack": (
                ("kind", inspect.Parameter.empty),
                ("target", inspect.Parameter.empty),
                ("ask", ""),
                ("lang", "en"),
                ("thread", None),
            ),
            "run_task": (
                ("kind", inspect.Parameter.empty),
                ("target", inspect.Parameter.empty),
                ("ask", ""),
                ("lang", "en"),
                ("thread", None),
            ),
            "error_label": (
                ("exc", inspect.Parameter.empty),
            ),
            "save_deliverable": (
                ("result", inspect.Parameter.empty),
                ("lang", "en"),
                ("title", ""),
            ),
            "list_deliverables": (
                ("limit", 50),
            ),
            "read_deliverable": (
                ("did", inspect.Parameter.empty),
                ("fmt", "md"),
            ),
        }

        for name, expected_shape in expected.items():
            with self.subTest(function=name):
                function = getattr(agents, name)
                actual_shape = tuple(
                    (parameter.name, parameter.default)
                    for parameter in inspect.signature(function).parameters.values()
                )
                self.assertEqual(actual_shape, expected_shape)

    def test_public_protocol_constants_are_stable(self):
        self.assertEqual(
            agents.TASK_KINDS,
            ("research_person", "research_company", "meeting_prep"),
        )
        self.assertEqual(agents.ALIAS, "agent@example.com")


if __name__ == "__main__":
    unittest.main()
