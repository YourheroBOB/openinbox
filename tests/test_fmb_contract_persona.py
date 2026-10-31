"""Contract tests for the public persona module interface.

All writes are redirected to a temporary directory. The fixtures contain only
reserved example.invalid addresses and obvious fake marker values.
"""
from __future__ import annotations

import inspect
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SERVER_DIR = ROOT / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import persona as persona_module


class PersonaPublicInterfaceContractTests(unittest.TestCase):
    def test_public_function_signatures_are_stable(self):
        self.assertEqual(list(inspect.signature(persona_module.rebuild).parameters), [])
        self.assertEqual(list(inspect.signature(persona_module.load).parameters), [])

    def test_rebuild_return_and_file_artifact_contract(self):
        fake_now = "2026-01-02T03:04:05+08:00"
        emails = [
            {
                "from_addr": "Sender <sender@example.invalid>",
                "category": "needs_you",
            },
            {
                "from_addr": "Sender <sender@example.invalid>",
                "category": "fyi",
            },
        ]
        config = {
            "mode": "demo",
            "accounts": [{"email": "owner@example.invalid"}],
        }
        board = {
            "todos": {
                "needs_you": [{"text": "FAKE_VALUE_FOR_TEST"}],
            }
        }

        with tempfile.TemporaryDirectory(prefix="openinbox-fmb-persona-") as temporary:
            temporary_path = Path(temporary)
            vault_path = temporary_path / "vault"
            persona_path = vault_path / "persona.json"
            missing_fixture = temporary_path / "missing-fixtures.json"

            with (
                mock.patch.object(persona_module, "ROOT", temporary_path),
                mock.patch.object(persona_module, "PERSONA_PATH", persona_path),
                mock.patch.object(persona_module, "FIXTURE", missing_fixture),
                mock.patch.object(persona_module, "list_emails", return_value=emails),
                mock.patch.object(persona_module, "brain_board", return_value=board),
                mock.patch.object(persona_module, "load_cfg", return_value=config),
                mock.patch.object(persona_module, "now_iso", return_value=fake_now),
            ):
                result = persona_module.rebuild()

                expected = {
                    "updated_at": fake_now,
                    "mode": "demo",
                    "identity": {
                        "name": "You",
                        "role": "Inbox owner",
                        "timezone": "local",
                        "accounts": ["owner@example.invalid"],
                    },
                    "how_you_write": [
                        "Learned from sent mail once a live driver is connected."
                    ],
                    "how_you_run_inbox": [
                        "Needs-you items first, then money, then the rest."
                    ],
                    "attention_now": ["FAKE_VALUE_FOR_TEST"],
                    "inbox_priorities": [
                        {"category": "needs_you", "count": 1},
                        {"category": "upcoming", "count": 0},
                        {"category": "worth_a_look", "count": 0},
                        {"category": "fyi", "count": 1},
                        {"category": "other", "count": 0},
                    ],
                    "top_senders": [
                        {"email": "sender@example.invalid", "count": 2}
                    ],
                    "facts_learned": 2,
                    "source": "local-mail",
                }
                self.assertEqual(result, expected)

                self.assertTrue(persona_path.is_file())
                persisted = json.loads(persona_path.read_text(encoding="utf-8"))
                self.assertEqual(persisted, result)

                markdown_path = persona_path.with_name("persona.md")
                self.assertTrue(markdown_path.is_file())
                markdown = markdown_path.read_text(encoding="utf-8")
                self.assertTrue(markdown.startswith("# 更了解你 / Know you better"))
                self.assertIn(f"Updated {fake_now}", markdown)
                self.assertIn("## 此刻要注意 / Attention now", markdown)
                self.assertIn("- FAKE_VALUE_FOR_TEST", markdown)
                self.assertIn("- sender@example.invalid (2)", markdown)

    def test_load_returns_the_existing_json_document(self):
        with tempfile.TemporaryDirectory(prefix="openinbox-fmb-persona-") as temporary:
            persona_path = Path(temporary) / "persona.json"
            payload = {"contract": "FAKE_VALUE_FOR_TEST"}
            persona_path.write_text(
                json.dumps(payload, ensure_ascii=False),
                encoding="utf-8",
            )

            with mock.patch.object(persona_module, "PERSONA_PATH", persona_path):
                self.assertEqual(persona_module.load(), payload)

    def test_load_invalid_json_raises_json_decode_error(self):
        with tempfile.TemporaryDirectory(prefix="openinbox-fmb-persona-") as temporary:
            persona_path = Path(temporary) / "persona.json"
            persona_path.write_text("{", encoding="utf-8")

            with mock.patch.object(persona_module, "PERSONA_PATH", persona_path):
                with self.assertRaises(json.JSONDecodeError):
                    persona_module.load()


if __name__ == "__main__":
    unittest.main()
