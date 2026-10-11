"""A tiny loopback IMAP4rev1 server for tests: enough of LOGIN / EXAMINE /
UID SEARCH / UID FETCH / LOGOUT for imaplib, with fictional example.com mail.
It records every command so tests can prove the driver stays read-only.
"""
from __future__ import annotations

import re
import socketserver
import threading
from email.message import EmailMessage
from email.utils import format_datetime
from datetime import datetime, timedelta, timezone

TZ8 = timezone(timedelta(hours=8))


def _plain(subject, frm, body, when, msgid, refs=None):
    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = frm, "you@example.com", subject
    m["Date"], m["Message-ID"] = format_datetime(when), msgid
    if refs:
        m["References"] = refs
    m.set_content(body)
    return m


def fictional_mail() -> list[dict]:
    base = datetime(2026, 9, 20, 9, 0, tzinfo=TZ8)
    m1 = _plain("Can you confirm the venue by Thursday?", "Rina Park <rina@harbor.example>",
                "Please confirm the venue by Thursday 17:00 so we can book it.", base, "<m1@harbor.example>")
    m2 = _plain("季度報告：請審閱附件", "Lin Studio <studio@lantern.example>",
                "附件是第三季報告草稿，請審閱。", base + timedelta(hours=1), "<m2@lantern.example>",
                refs="<root2@lantern.example>")
    m2.add_attachment(b"%PDF-1.4 fictional", maintype="application", subtype="pdf", filename="q3-draft.pdf")
    m3 = EmailMessage()
    m3["From"], m3["To"] = "Tidepool News <newsletter@tidepool.example>", "you@example.com"
    m3["Subject"], m3["Date"] = "Weekly digest", format_datetime(base + timedelta(hours=2))
    m3["Message-ID"] = "<m3@tidepool.example>"
    m3.set_content("<html><style>p{}</style><body><p>Hello &amp; welcome</p>"
                   "<a href='https://tidepool.example/u'>unsubscribe</a></body></html>", subtype="html")
    return [
        {"uid": 101, "flags": [r"\Seen"], "raw": m1.as_bytes()},
        {"uid": 102, "flags": [r"\Flagged"], "raw": m2.as_bytes()},
        {"uid": 105, "flags": [], "raw": m3.as_bytes()},
    ]


def _imap_args(text: str) -> list[str]:
    out, i = [], 0
    while i < len(text):
        if text[i] == " ":
            i += 1
        elif text[i] == '"':
            j, buf = i + 1, []
            while text[j] != '"':
                if text[j] == "\\":
                    j += 1
                buf.append(text[j])
                j += 1
            out.append("".join(buf))
            i = j + 1
        else:
            j = text.find(" ", i)
            j = len(text) if j < 0 else j
            out.append(text[i:j])
            i = j
    return out


class FakeIMAP:
    def __init__(self, user="you@example.com", password="fake-app-pass", mail=None, uidvalidity=7):
        self.user, self.password, self.uidvalidity = user, password, uidvalidity
        self.mail = mail if mail is not None else fictional_mail()
        self.commands: list[str] = []
        owner = self

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                owner._session(self.rfile, self.wfile)

        self.server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def verbs(self) -> list[str]:
        out = []
        for c in self.commands:
            parts = c.split(" ")
            verb = parts[0].upper()
            out.append(f"{verb} {parts[1].upper()}" if verb == "UID" and len(parts) > 1 else verb)
        return out

    def _session(self, rfile, wfile):
        w = lambda s: (wfile.write(s if isinstance(s, bytes) else s.encode()), wfile.flush())
        w("* OK [CAPABILITY IMAP4rev1] fake ready\r\n")
        authed = False
        while True:
            line = rfile.readline()
            if not line:
                return
            tag, _, rest = line.decode().rstrip("\r\n").partition(" ")
            cmd, _, args = rest.partition(" ")
            cmd = cmd.upper()
            self.commands.append(rest if cmd != "LOGIN" else "LOGIN <redacted>")
            if cmd == "CAPABILITY":
                w("* CAPABILITY IMAP4rev1 AUTH=PLAIN\r\n" + f"{tag} OK done\r\n")
            elif cmd == "NOOP":
                w(f"{tag} OK done\r\n")
            elif cmd == "LOGIN":
                user, pw = (_imap_args(args) + ["", ""])[:2]
                authed = user == self.user and pw == self.password
                w(f"{tag} OK logged in\r\n" if authed else f"{tag} NO [AUTHENTICATIONFAILED] Invalid credentials\r\n")
            elif cmd == "LOGOUT":
                w("* BYE bye\r\n" + f"{tag} OK done\r\n")
                return
            elif not authed:
                w(f"{tag} NO login first\r\n")
            elif cmd in ("EXAMINE", "SELECT"):
                mode = "READ-ONLY" if cmd == "EXAMINE" else "READ-WRITE"
                w(f"* {len(self.mail)} EXISTS\r\n* 0 RECENT\r\n* FLAGS (\\Seen \\Flagged)\r\n"
                  f"* OK [UIDVALIDITY {self.uidvalidity}] ok\r\n{tag} OK [{mode}] done\r\n")
            elif cmd == "UID":
                sub, _, sargs = args.partition(" ")
                sub = sub.upper()
                if sub == "SEARCH":
                    w("* SEARCH " + " ".join(str(m["uid"]) for m in self.mail) + f"\r\n{tag} OK done\r\n")
                elif sub == "FETCH":
                    uidset, _, items = sargs.partition(" ")
                    want = {int(u) for u in uidset.split(",")}
                    cap = re.search(r"BODY\.PEEK\[\]<0\.(\d+)>", items)
                    for seq, m in enumerate(self.mail, 1):
                        if m["uid"] not in want:
                            continue
                        raw = m["raw"][: int(cap.group(1))] if cap else m["raw"]
                        head = (f'* {seq} FETCH (UID {m["uid"]} FLAGS ({" ".join(m["flags"])}) '
                                f'INTERNALDATE "20-Sep-2026 09:00:00 +0800" BODY[]<0> {{{len(raw)}}}\r\n')
                        w(head.encode() + raw + b")\r\n")
                    w(f"{tag} OK done\r\n")
                else:
                    w(f"{tag} BAD unsupported in fake\r\n")
            else:
                w(f"{tag} BAD unsupported in fake\r\n")
