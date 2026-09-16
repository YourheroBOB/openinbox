#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v python3 >/dev/null; then
  echo "Need python3 3.9+"
  exit 1
fi

python3 - <<'PY'
import sys
if sys.version_info < (3, 9):
    raise SystemExit("Need python3 3.9+")
print("python", sys.version.split()[0])
PY

mkdir -p data vault/cards
[[ -f accounts.json ]] || cp accounts.example.json accounts.json
[[ -f agent.json ]] || cp agent.example.json agent.json

echo
echo "TooPowerInbox is ready. ／ TooPowerInbox 已就緒。"
echo "  Demo mode is on by default (no mail login required)."
echo "  預設示範模式，不必登信箱。"
echo "  Start:  ./run.sh"
echo "  Then:   http://127.0.0.1:8770/"
echo
echo "Language: click 繁中 / EN, or ?lang=zh-Hant / ?lang=en"
echo "語系：左側按 繁中／EN，或用網址參數。"
echo
echo "To use real mail later, edit accounts.json:"
echo "之後要接真信箱，改 accounts.json："
echo "  driver=gog     for Gmail via https://gogcli.sh"
echo "  driver=gsk     for Outlook via Genspark CLI (transport only)"
echo "Bring your own agent in agent.json (local / openai_compatible / cli / http)."
echo "在 agent.json 帶進你自己的 Agent。"
