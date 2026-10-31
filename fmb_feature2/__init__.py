"""fmb_feature2: self-contained additions for openinbox.

This round: RFC 3501 modified UTF-7 mailbox names, read-only LIST parsing, and an
offline preflight for the IMAP entries in accounts.json. Nothing here imports the app;
copy the modules into server/features/ when you want them wired up (see README.md).
"""
