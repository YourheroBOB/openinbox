"""IMAP mailbox names offline: RFC 3501 modified UTF-7 and read-only LIST parsing.

Why this file
-------------
`server/features/imap.py` opens mailboxes read-only (EXAMINE + BODY.PEEK), but the mailbox
*name* still has to survive the wire. IMAP carries ASCII only: every character outside
U+0020..U+007E travels as a base64 chunk of UTF-16BE wrapped in `&` ... `-`, with `,`
standing in for `/`. So a folder called 台北 has to be encoded before EXAMINE, and names
coming back from LIST have to be decoded before a human reads them. `state/tpi-providers.md`
lists exactly this as the next step ("IMAP 多 mailbox 與非 ASCII 資料夾名稱（modified UTF-7）").

What is in here
---------------
- `encode_mailbox()` / `decode_mailbox()`: the codec, strict by default, round-trippable.
- `parse_list_line()` / `parse_list_response()`: `* LIST (\\HasNoChildren) "/" "..."`
  into plain dicts — decoded name, flags, hierarchy delimiter, `selectable` (a `\\Noselect`
  folder is a container and must never be EXAMINEd) and depth.
- `audit_accounts()`: an offline preflight over an `accounts.json` dict. Reports the
  encoded mailbox name, which environment variable the password should come from, and
  warnings (a plaintext `password` key, `security: "none"` off loopback, very long names).
  It never echoes a credential value.
- `default_password_env()`: the `TPI_IMAP_PASSWORD_<EMAIL>` fallback variable name.

Rules kept: standard library only, no network module import, no files written, every
function pure, so the whole file is testable with throwaway strings.
"""
from __future__ import annotations

import base64
import binascii
import json
import re
import sys
from pathlib import Path

SHIFT = "&"
MAX_ENCODED_LEN = 255
LOOPBACK_HOSTS = ("localhost", "localhost.localdomain", "::1")

_LIST_HEAD = re.compile(r"^\*\s+(LIST|LSUB)\s+", re.IGNORECASE)
_ATOM = re.compile(r"[^ \t]+")

__all__ = [
    "MailboxNameError",
    "encode_mailbox",
    "decode_mailbox",
    "needs_encoding",
    "parse_list_line",
    "parse_list_response",
    "audit_accounts",
    "default_password_env",
    "MAX_ENCODED_LEN",
]


class MailboxNameError(ValueError):
    """A mailbox name or a LIST line that does not follow RFC 3501."""


# ───────────────────────── codec ─────────────────────────

def encode_mailbox(name: str) -> str:
    """Encode one mailbox name for the wire. Pure; raises MailboxNameError on bad input."""
    if not isinstance(name, str):
        raise MailboxNameError("mailbox name must be a string")
    if not name:
        raise MailboxNameError("mailbox name is empty")
    if "\x00" in name:
        raise MailboxNameError("mailbox name must not contain NUL")

    out: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if not pending:
            return
        try:
            raw = "".join(pending).encode("utf-16-be")
        except UnicodeEncodeError as exc:  # a lone surrogate has no UTF-16BE form
            raise MailboxNameError("mailbox name has an unpaired surrogate") from exc
        chunk = base64.b64encode(raw).decode("ascii").rstrip("=").replace("/", ",")
        out.append(SHIFT + chunk + "-")
        pending.clear()

    for ch in name:
        if " " <= ch <= "~":
            flush()
            out.append("&-" if ch == SHIFT else ch)
        else:
            pending.append(ch)
    flush()
    return "".join(out)


def decode_mailbox(text: str, *, strict: bool = True) -> str:
    """Decode a mailbox name coming off the wire.

    `strict` (default) rejects an `&` escape with no closing `-`; pass `strict=False` to
    read such a name to the end of the string instead. Raises MailboxNameError.
    """
    if not isinstance(text, str):
        raise MailboxNameError("mailbox name must be a string")
    if SHIFT not in text:
        return text

    out: list[str] = []
    i, size = 0, len(text)
    while i < size:
        ch = text[i]
        if ch != SHIFT:
            out.append(ch)
            i += 1
            continue
        end = text.find("-", i + 1)
        if end < 0:
            if strict:
                raise MailboxNameError("unterminated '&' escape in mailbox name")
            body, i = text[i + 1:], size
        else:
            body, i = text[i + 1:end], end + 1
        if body == "":
            out.append(SHIFT)
            continue
        chunk = body.replace(",", "/")
        if len(chunk) % 4 == 1:
            raise MailboxNameError("base64 length in '&' escape is impossible")
        try:
            raw = base64.b64decode(chunk + "=" * (-len(chunk) % 4), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise MailboxNameError("bad base64 in '&' escape") from exc
        if len(raw) % 2:
            raise MailboxNameError("'&' escape is not a whole number of UTF-16 units")
        try:
            out.append(raw.decode("utf-16-be"))
        except UnicodeDecodeError as exc:
            raise MailboxNameError("'&' escape is not valid UTF-16") from exc
    return "".join(out)


def needs_encoding(name: str) -> bool:
    """True when the wire form differs from the name as typed (wide chars or `&`)."""
    return encode_mailbox(name) != name


# ───────────────────────── LIST parsing ─────────────────────────

def _token(text: str) -> tuple[str, str, bool]:
    """Read one IMAP token: (value, rest, was_quoted)."""
    s = text.lstrip(" \t")
    if not s:
        raise MailboxNameError("response line ended early")
    if s[0] == "{":
        raise MailboxNameError("literal values continue on the next line; not supported offline")
    if s[0] == '"':
        buf: list[str] = []
        i = 1
        while i < len(s):
            ch = s[i]
            if ch == "\\":
                if i + 1 >= len(s):
                    raise MailboxNameError("quoted value ends with a lone backslash")
                nxt = s[i + 1]
                if nxt not in ('"', "\\"):
                    raise MailboxNameError('only \\" and \\\\ are escaped inside a quoted value')
                buf.append(nxt)
                i += 2
                continue
            if ch == '"':
                return "".join(buf), s[i + 1:], True
            buf.append(ch)
            i += 1
        raise MailboxNameError("unterminated quoted value")
    atom = _ATOM.match(s)
    if not atom:
        raise MailboxNameError("response line ended early")
    return atom.group(0), s[atom.end():], False


def _flags(text: str) -> tuple[list[str], str]:
    s = text.lstrip(" \t")
    if not s.startswith("("):
        raise MailboxNameError("LIST response is missing its flag list")
    end = s.find(")")
    if end < 0:
        raise MailboxNameError("unterminated flag list")
    flags = []
    for part in s[1:end].split():
        if len(part) >= 2 and part[0] == part[-1] == '"':
            flags.append(part[1:-1])
        else:
            flags.append(part)
    return flags, s[end + 1:]


def parse_list_line(line: str) -> dict:
    """Parse one `* LIST` / `* LSUB` line into a plain dict. Pure; raises MailboxNameError."""
    text = (line or "").strip()
    head = _LIST_HEAD.match(text)
    if not head:
        raise MailboxNameError("not a LIST or LSUB response line")
    rest = text[head.end():]
    flags, rest = _flags(rest)
    delimiter, rest, delimiter_quoted = _token(rest)
    if not delimiter_quoted and delimiter.upper() == "NIL":
        delimiter = None  # flat namespace: no hierarchy separator
    name_raw, rest, name_quoted = _token(rest)
    if not name_quoted and name_raw.upper() == "NIL":
        raise MailboxNameError("LIST response has NIL for the mailbox name")
    if rest.strip():
        raise MailboxNameError("unexpected trailing data after the mailbox name")
    name = decode_mailbox(name_raw)
    return {
        "kind": head.group(1).upper(),
        "flags": flags,
        "delimiter": delimiter,
        "raw_name": name_raw,
        "name": name,
        "selectable": not any(f.lower() == "\\noselect" for f in flags),
        "depth": name.count(delimiter) if delimiter else 0,
    }


def parse_list_response(text: str) -> list[dict]:
    """Parse a whole LIST transcript. Other untagged/tagged lines are ignored on purpose;
    a line that starts like LIST but is malformed still raises, so bad data is never dropped
    silently."""
    entries = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped or not _LIST_HEAD.match(stripped):
            continue
        entries.append(parse_LIST_LINE_SAFE(stripped))
    return entries


def parse_LIST_LINE_SAFE(line: str) -> dict:  # noqa: N802 - kept as a small alias
    return parse_list_line(line)


# ───────────────────────── config preflight ─────────────────────────

def default_password_env(email: str) -> str:
    """The environment variable the IMAP driver falls back to for this account."""
    return "TPI_IMAP_PASSWORD_" + re.sub(r"[^A-Z0-9]", "_", (email or "").upper())


def _is_loopback(host: str) -> bool:
    h = (host or "").strip().strip("[]").lower()
    if not h:
        return False
    return h in LOOPBACK_HOSTS or h.startswith("127.")


def audit_accounts(cfg) -> dict:
    """Describe the IMAP-relevant parts of an accounts.json dict without touching a secret.

    Returns {"mode", "accounts": [...], "warnings": [...], "ok"}. Each account entry carries
    the mailbox as typed, its wire form, whether encoding changes anything, the environment
    variable the password should come from, and the transport security. Credential *values*
    are never copied into the report.
    """
    accounts = cfg.get("accounts") if isinstance(cfg, dict) else None
    if not isinstance(accounts, list):
        accounts = []
    entries: list[dict] = []
    warnings: list[str] = []
    for index, acc in enumerate(accounts):
        label = "account %d" % (index + 1)
        if not isinstance(acc, dict):
            warnings.append(label + ": not an object, skipped")
            continue
        email = str(acc.get("email") or "")
        driver = str(acc.get("driver") or "")
        mailbox = str(acc.get("mailbox") or "INBOX")
        encoded = ""
        try:
            encoded = encode_mailbox(mailbox)
        except MailboxNameError as exc:
            warnings.append(label + ": mailbox name rejected (" + str(exc) + ")")
        security = str(acc.get("security") or ("ssl" if driver == "imap" else ""))
        env = str(acc.get("password_env") or (default_password_env(email) if driver == "imap" else ""))
        entries.append({
            "index": index,
            "email": email,
            "driver": driver,
            "mailbox": mailbox,
            "encoded": encoded,
            "needs_encoding": bool(encoded) and encoded != mailbox,
            "password_env": env,
            "security": security,
        })
        if encoded and len(encoded) > MAX_ENCODED_LEN:
            warnings.append(label + ": encoded mailbox name is " + str(len(encoded))
                            + " bytes; many servers cap a mailbox name at 255")
        if "password" in acc:
            warnings.append(label + ": plaintext 'password' key present; keep the secret in "
                            + (env or "a password_env variable") + " (value not shown)")
        if driver == "imap":
            if security.lower() == "none" and not _is_loopback(str(acc.get("host") or "")):
                warnings.append(label + ": security 'none' is only for a loopback host; use ssl or starttls")
            if not env:
                warnings.append(label + ": no password_env and no email to derive one from")
    return {
        "mode": str(cfg.get("mode") or "") if isinstance(cfg, dict) else "",
        "accounts": entries,
        "warnings": warnings,
        "ok": not warnings,
    }


# ───────────────────────── CLI (offline, read only) ─────────────────────────

_USAGE = (
    "usage: imap_mailbox.py encode <name>\n"
    "       imap_mailbox.py decode <wire-name>\n"
    "       imap_mailbox.py list <file-with-LIST-lines|->\n"
    "       imap_mailbox.py audit <accounts.json>"
)


def _main(argv) -> int:
    if len(argv) < 2 or argv[0] not in ("encode", "decode", "list", "audit"):
        print(_USAGE, file=sys.stderr)
        return 2
    command, argument = argv[0], argv[1]
    try:
        if command == "encode":
            print(encode_mailbox(argument))
        elif command == "decode":
            print(decode_mailbox(argument))
        elif command == "list":
            if argument == "-":
                text = sys.stdin.read()
            else:
                text = Path(argument).read_text(encoding="utf-8", errors="replace")
            print(json.dumps(parse_list_response(text), ensure_ascii=False, indent=2))
        else:
            cfg = json.loads(Path(argument).read_text(encoding="utf-8"))
            print(json.dumps(audit_accounts(cfg), ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
