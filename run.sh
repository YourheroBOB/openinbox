#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
[[ -f accounts.json ]] || ./install.sh
export OPENINBOX_ROOT="$ROOT"
export OPENINBOX_PORT="${OPENINBOX_PORT:-8770}"
exec python3 "$ROOT/server/app.py"
