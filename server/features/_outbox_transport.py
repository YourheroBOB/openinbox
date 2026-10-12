"""Outbox transport interface. TooPowerInbox ships with no delivery transport at all.

A transport would take a released `.eml` and hand it to some delivery system. The
only one that exists is `disabled`: it never delivers, so every released message
stays in `data/outbox/` marked "awaiting the user to send it themselves".

This file is the seam, not an invitation: there is no network, socket or mail
protocol code here, and `get()` refuses any name that is not registered. A
transport's `deliver()` is only ever called when `enabled` is True, and the
outbox never calls it for a message the user has not confirmed.

The released `.eml` keeps `Bcc` and `X-Unsent: 1` so the user can open it in a mail
client. A later transport that hands those bytes to SMTP must strip `Bcc` first;
sending the file as stored would leak blind-copy recipients.
"""
from __future__ import annotations

from pathlib import Path


class Transport:
    """What a transport must provide. Subclasses describe themselves and deliver one file."""

    name = "base"
    enabled = False
    label_en = "Base transport"
    label_zh = "基底傳輸"

    def describe(self, zh: bool = False) -> dict:
        return {"name": self.name, "enabled": self.enabled, "label": self.label_zh if zh else self.label_en}

    def deliver(self, eml_path: Path, meta: dict) -> dict:
        """Return {"delivered": bool, "detail": str}. Must not be called when `enabled` is False."""
        raise NotImplementedError


class DisabledTransport(Transport):
    name = "disabled"
    enabled = False
    label_en = "Disabled: released mail is written as .eml and waits for you to send it yourself"
    label_zh = "未啟用：到期的信只寫成 .eml，待你自行寄出"

    def deliver(self, eml_path: Path, meta: dict) -> dict:
        return {"delivered": False, "detail": "no transport configured"}


REGISTRY: dict[str, type[Transport]] = {"disabled": DisabledTransport}
DEFAULT = "disabled"


def names() -> list[str]:
    return list(REGISTRY)


def get(name: str | None = None) -> Transport:
    cls = REGISTRY.get(name or DEFAULT)
    if cls is None:
        raise KeyError(f"unknown transport {name!r}; registered: {', '.join(REGISTRY)}")
    return cls()
