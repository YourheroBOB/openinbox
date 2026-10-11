#!/usr/bin/env bash
# Run the `run:` steps of .github/workflows/smoke.yml locally on Linux, in order,
# against a throwaway copy of the working tree (tracked + untracked, minus
# .gitignore'd files), so local accounts.json / agent.json / data/ stay untouched.
#
#   scripts/smoke.sh                 # port 8770, or a free port if 8770 is taken
#   SMOKE_PORT=8899 scripts/smoke.sh
#   SMOKE_KEEP=1 scripts/smoke.sh    # keep the scratch copy and server log
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORKFLOW="$ROOT/.github/workflows/smoke.yml"
command -v python3 >/dev/null || { echo "smoke: need python3" >&2; exit 1; }
command -v curl >/dev/null || { echo "smoke: need curl" >&2; exit 1; }
[[ -f "$WORKFLOW" ]] || { echo "smoke: missing $WORKFLOW" >&2; exit 1; }

port_free() {
  python3 - "$1" <<'PY'
import socket, sys
s = socket.socket()
try:
    s.bind(("127.0.0.1", int(sys.argv[1])))
except OSError:
    sys.exit(1)
finally:
    s.close()
PY
}

if [[ -n "${SMOKE_PORT:-}" ]]; then
  PORT="$SMOKE_PORT"
  port_free "$PORT" || { echo "smoke: port $PORT is busy" >&2; exit 1; }
else
  PORT=8770
  if ! port_free "$PORT"; then
    PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
    echo "smoke: 8770 is busy, using $PORT"
  fi
fi

SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/tpi-smoke.XXXXXX")"
WORK="$SCRATCH/repo"
STEPS="$SCRATCH/steps"
LOG="$SCRATCH/server.log"
SERVER_PID=""

cleanup() {
  local code=$?
  if [[ -n "$SERVER_PID" ]]; then
    kill -TERM -- "-$SERVER_PID" 2>/dev/null || kill -TERM "$SERVER_PID" 2>/dev/null || true
    pkill -TERM -P "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  if [[ $code -ne 0 && -s "$LOG" ]]; then
    echo "── server log ──" >&2
    tail -n 40 "$LOG" >&2
  fi
  if [[ "${SMOKE_KEEP:-0}" == "1" ]]; then
    echo "smoke: kept $SCRATCH"
  else
    rm -rf "$SCRATCH"
  fi
  exit "$code"
}
trap cleanup EXIT INT TERM

mkdir -p "$WORK" "$STEPS"
python3 - "$ROOT" "$WORK" <<'PY'
import os, shutil, subprocess, sys
src, dst = sys.argv[1], sys.argv[2]
out = subprocess.run(["git", "-C", src, "ls-files", "-z", "-co", "--exclude-standard"],
                     check=True, capture_output=True).stdout
for rel in filter(None, out.decode().split("\0")):
    p = os.path.join(src, rel)
    if os.path.isfile(p):
        os.makedirs(os.path.dirname(os.path.join(dst, rel)), exist_ok=True)
        shutil.copy2(p, os.path.join(dst, rel))
PY

python3 - "$WORKFLOW" "$STEPS" "$PORT" <<'PY'
import re, sys
from pathlib import Path

workflow, out_dir, port = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
lines = workflow.read_text().splitlines()
key = re.compile(r"^(\s*)(-\s+)?run:\s*(.*)$")
steps, i = [], 0
while i < len(lines):
    m = key.match(lines[i])
    i += 1
    if not m:
        continue
    indent = len(m.group(1)) + len(m.group(2) or "")
    value = m.group(3).strip()
    if value[:1] in ("|", ">"):
        block = []
        while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > indent):
            block.append(lines[i])
            i += 1
        while block and not block[-1].strip():
            block.pop()
        pad = min(len(b) - len(b.lstrip()) for b in block if b.strip())
        script = "\n".join(b[pad:] for b in block)
    else:
        if len(value) > 1 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        script = value
    for host in ("127.0.0.1", "localhost"):
        script = script.replace(f"{host}:8770", f"{host}:{port}")
    background = "\n" not in script and script.rstrip().endswith("&")
    if background:
        script = script.rstrip()[:-1].rstrip()
    steps.append((background, script))
if not steps:
    sys.exit("smoke: no run steps found in workflow")
for n, (background, script) in enumerate(steps, 1):
    (out_dir / f"{n:02d}.{'bg' if background else 'fg'}.sh").write_text(script + "\n")
PY

export OPENINBOX_PORT="$PORT"
export OPENINBOX_NO_BROWSER=1
cd "$WORK"
total=0
for step in "$STEPS"/*.sh; do
  total=$((total + 1))
  name="$(basename "$step")"
  printf '\n▶ step %s: %s\n' "${name%%.*}" "$(head -n 1 "$step")"
  if [[ "$name" == *.bg.sh ]]; then
    if command -v setsid >/dev/null; then
      setsid bash --noprofile --norc -e "$step" >"$LOG" 2>&1 &
    else
      bash --noprofile --norc -e "$step" >"$LOG" 2>&1 &
    fi
    SERVER_PID=$!
  else
    bash --noprofile --norc -eo pipefail "$step"
  fi
done

echo
echo "smoke: OK ($total steps from $(basename "$WORKFLOW"), port $PORT)"
