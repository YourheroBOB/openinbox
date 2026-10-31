"""Contract tests for the optional IMAP mailbox-audit route glue."""
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class FeatureImapMailboxContractTests(unittest.TestCase):
    def test_get_route_passes_loaded_config_to_audit_function(self):
        registered_routes = {}
        config = {"mode": "demo", "accounts": []}
        response = {"accounts": [], "warnings": []}
        audit_calls = []
        config_loads = []

        def get(path):
            def register(handler):
                registered_routes[path] = handler
                return handler

            return register

        def load_cfg():
            config_loads.append(True)
            return config

        def audit_accounts(received_config):
            audit_calls.append(received_config)
            return response

        features_package = types.ModuleType("features")
        features_package.__path__ = []
        features_package.get = get

        audit_module = types.ModuleType("features.imap_mailbox")
        audit_module.audit_accounts = audit_accounts

        yhbmail_module = types.ModuleType("yhbmail")
        yhbmail_module.load_cfg = load_cfg

        source = (
            Path(__file__).resolve().parents[1]
            / "fmb_feature2"
            / "feature_imap_mailbox.py"
        )
        spec = importlib.util.spec_from_file_location(
            "_fmb_contract_feature_imap_mailbox", source
        )
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)

        stubs = {
            "features": features_package,
            "features.imap_mailbox": audit_module,
            "yhbmail": yhbmail_module,
        }
        with patch.dict(sys.modules, stubs):
            spec.loader.exec_module(module)

            self.assertEqual(
                set(registered_routes),
                {"/api/imap/mailbox-audit"},
            )
            self.assertIs(
                registered_routes["/api/imap/mailbox-audit"],
                module.mailbox_audit,
            )
            self.assertIs(module.mailbox_audit(object()), response)

        self.assertEqual(len(config_loads), 1)
        self.assertEqual(len(audit_calls), 1)
        self.assertIs(audit_calls[0], config)


if __name__ == "__main__":
    unittest.main()
