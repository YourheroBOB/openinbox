#!/usr/bin/env python3
"""TooPowerInbox overnight agent: one pass, then a morning handoff brief.

Sync (optional), Super Agent triage, automation rules (dry run unless --apply-rules),
follow-ups waiting on others, local reply / nudge drafts, and a Markdown brief in
data/briefs/ (latest copy: data/briefs/latest.md). Nothing is sent; drafts stay local.

    python3 scripts/overnight.py                      # sync + triage + rules dry run + drafts + brief
    python3 scripts/overnight.py --no-sync --lang en  # use the local cache only, English brief
    python3 scripts/overnight.py --apply-rules        # also apply the rules (local labels / archive / drafts)

Cron example (06:00 every day):
    0 6 * * * cd /path/to/openinbox && python3 scripts/overnight.py >> data/overnight.log 2>&1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Overnight triage + drafts + morning brief (local only, never sends).")
    p.add_argument("--root", help="app root with accounts.json / data/ (default: this repo, or $OPENINBOX_ROOT)")
    p.add_argument("--lang", default="zh-Hant", help="brief language: zh-Hant (default) or en")
    p.add_argument("--no-sync", action="store_true", help="skip mail sync and use the local cache")
    p.add_argument("--apply-rules", action="store_true", help="apply the automation rules instead of a dry run")
    p.add_argument("--no-drafts", action="store_true", help="do not prepare reply / nudge drafts")
    p.add_argument("--max-drafts", type=int, default=10, help="new drafts per run (default 10)")
    p.add_argument("--days", type=int, help="follow-up threshold in days (default: saved setting, 3)")
    p.add_argument("--now", help="pretend it is this time (YYYY-MM-DD or YYYY-MM-DD HH:MM), for testing")
    p.add_argument("--sync-limit", type=int, default=25, help="messages per account to sync")
    p.add_argument("--print", dest="print_brief", action="store_true", help="print the brief to stdout")
    p.add_argument("--json", action="store_true", help="print the run summary as JSON")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.root:
        os.environ["OPENINBOX_ROOT"] = str(Path(args.root).resolve())
    os.environ.setdefault("OPENINBOX_ROOT", str(REPO))
    sys.path.insert(0, str(REPO / "server"))

    import features
    import yhbmail

    def fixture(name: str) -> Path:
        p = yhbmail.ROOT / "fixtures" / name
        return p if p.exists() else REPO / "fixtures" / name

    yhbmail.FIXTURE = fixture("demo_inbox.json")
    yhbmail.init_db()
    if args.no_sync and not yhbmail.counts()["emails"]:
        cfg = yhbmail.load_cfg()
        if (cfg.get("mode") or "demo") == "demo":
            yhbmail.seed_demo()
    features.load_all()
    if "overnight" not in features.LOADED:
        print("overnight: feature module failed to load: " + json.dumps(features.ERRORS, ensure_ascii=False),
              file=sys.stderr)
        return 2
    from features import followup, overnight, rules

    followup.SENT_FIXTURE = fixture("demo_sent.json")
    followup.DEMO_FIXTURE = fixture("followup_demo.json")
    rules.DEMO_RULES = fixture("rules_demo.json")

    out, status = overnight.run(
        lang=args.lang, sync=not args.no_sync, apply_rules=args.apply_rules, drafts=not args.no_drafts,
        max_drafts=args.max_drafts, now=args.now, days=args.days, source="script", sync_limit=args.sync_limit)
    if status != 200:
        print(f"overnight: {out.get('error')}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"ok": out["ok"], "id": out["id"], "brief_path": out["brief_path"],
                          "summary": out["summary"], "errors": out["data"]["errors"]}, ensure_ascii=False, indent=2))
    elif args.print_brief:
        print(out["markdown"])
    else:
        s = out["summary"]
        print(f"overnight #{out['id']}: needs_you={s['needs_you']} overdue={s['overdue']} "
              f"rules_matched={s['rules_matched']} ({'dry run' if s['rules_dry_run'] else 'applied'}) "
              f"drafts_new={s['drafts_new']} sent=0")
        print(f"brief: {out['brief_path']}")
        for e in out["data"]["errors"]:
            print(f"note: {e}", file=sys.stderr)
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
