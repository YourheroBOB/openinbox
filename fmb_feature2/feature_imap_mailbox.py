"""Optional glue: expose the offline IMAP preflight as one read-only route.

Copy this file *and* `imap_mailbox.py` into `server/features/`; the plug-in loader in
`server/features/__init__.py` registers `GET /api/imap/mailbox-audit` and nothing else has
to change (no edit to `server/app.py`).

The route reads the config dict (`yhbmail.load_cfg()`) and describes it: mailbox names in
their wire form, the environment variable each password should come from, warnings. It
never opens a mailbox, never logs in, never sends mail and never returns a credential
value.

Outside `server/features/` the guarded imports below fail and the module still imports
cleanly, so this file can be tested from `fmb_feature2/` on its own.
"""
from __future__ import annotations

try:  # only importable once this file lives in server/features/
    from features import get
except Exception:  # pragma: no cover - keeps the file importable on its own
    get = None

try:
    from features.imap_mailbox import audit_accounts
except Exception:  # pragma: no cover
    try:
        from imap_mailbox import audit_accounts
    except Exception:  # pragma: no cover
        audit_accounts = None


if get is not None and audit_accounts is not None:

    @get("/api/imap/mailbox-audit")
    def mailbox_audit(req):
        """Offline preflight of the IMAP settings. Read only; no credential value leaves here."""
        import yhbmail

        return audit_accounts(yhbmail.load_cfg())
