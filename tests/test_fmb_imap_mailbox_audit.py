"""Offline tests for the optional IMAP mailbox audit."""

import base64
import imaplib
import json
import os
import socket
import unittest
from unittest import mock

from fmb_feature2.imap_mailbox import audit_accounts


def _modified_utf7_for_non_ascii(text):
    """Encode a wholly non-ASCII mailbox name as an RFC 3501 modified UTF-7 run."""
    encoded = base64.b64encode(text.encode("utf-16-be")).decode("ascii")
    return "&" + encoded.rstrip("=").replace("/", ",") + "-"


class ImapMailboxAuditTests(unittest.TestCase):
    def audit_without_network(self, config):
        with (
            mock.patch("socket.socket", side_effect=AssertionError("network access is not allowed")) as socket_call,
            mock.patch.object(imaplib, "IMAP4", side_effect=AssertionError("network access is not allowed")) as imap_call,
            mock.patch.object(imaplib, "IMAP4_SSL", side_effect=AssertionError("network access is not allowed")) as imaps_call,
        ):
            result = audit_accounts(config)

        socket_call.assert_not_called()
        imap_call.assert_not_called()
        imaps_call.assert_not_called()
        return result

    def test_audit_reports_wire_mailbox_and_env_name_without_exposing_value(self):
        env_name = "FAKE_IMAP_PASSWORD_ENV"
        secret = "FAKE_VALUE_FOR_TEST"
        mailbox = "團隊"
        config = {
            "mode": "live",
            "accounts": [
                {
                    "email": "tester@example.test",
                    "driver": "imap",
                    "host": "imap.example.test",
                    "port": 993,
                    "security": "ssl",
                    "username": "tester@example.test",
                    "password_env": env_name,
                    "mailbox": mailbox,
                }
            ],
        }

        with mock.patch.dict(os.environ, {env_name: secret}):
            report = self.audit_without_network(config)

        rendered = json.dumps(report, ensure_ascii=False)
        self.assertIn(env_name, rendered)
        self.assertIn(_modified_utf7_for_non_ascii(mailbox), rendered)
        self.assertNotIn(secret, rendered)

    def test_audit_uses_inbox_as_the_default_mailbox(self):
        config = {
            "mode": "live",
            "accounts": [
                {
                    "email": "tester@example.test",
                    "driver": "imap",
                    "host": "imap.example.test",
                    "username": "tester@example.test",
                    "password_env": "FAKE_IMAP_PASSWORD_ENV",
                }
            ],
        }

        report = self.audit_without_network(config)

        self.assertIn("INBOX", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
