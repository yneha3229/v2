#!/usr/bin/env bash
# One-command setup + start for Proofroom (Linux, macOS, and Git Bash on Windows).
#
#   ./run.sh              # set up (first time) and start the demo on http://localhost:8000/demo
#   PORT=9000 ./run.sh    # another port
#   SKIP_PDF=1 ./run.sh   # skip the Node/Playwright setup (PDF download button won't work)
#
# Live search for new companies needs CRUSTDATA_API_KEY in .env (the 9 recorded companies
# work without any key). The key is never printed.
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8000}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }

# 1. Python 3.12+ ------------------------------------------------------------------------
PY=""
for cand in python3.12 python3 python "py -3.12" "py -3"; do
  if $cand -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
    PY="$cand"; break
  fi
done
[ -n "$PY" ] || { echo "Python 3.12+ not found. Install it from https://www.python.org/downloads/ and re-run."; exit 1; }
say "Using $($PY --version 2>&1)"

# 2. Virtual environment + dependencies -------------------------------------------------
if [ ! -d .venv ]; then
  say "Creating virtual environment (.venv)"
  $PY -m venv .venv
fi
if [ -x .venv/bin/python ]; then VPY=.venv/bin/python; else VPY=.venv/Scripts/python.exe; fi
STAMP=.venv/.requirements.sha
REQ_SHA="$($VPY -c 'import hashlib;print(hashlib.sha256(open("requirements.txt","rb").read()).hexdigest())')"
if [ ! -f "$STAMP" ] || [ "$(cat "$STAMP")" != "$REQ_SHA" ]; then
  say "Installing Python dependencies"
  $VPY -m pip install --quiet --upgrade pip
  $VPY -m pip install --quiet -r requirements.txt
  echo "$REQ_SHA" > "$STAMP"
else
  say "Python dependencies already installed"
fi

# 3. .env (keys stay local and git-ignored) ----------------------------------------------
if [ ! -f .env ]; then
  if [ -f .env.example ]; then cp .env.example .env; else : > .env; fi
  warn ".env created. Add CRUSTDATA_API_KEY=... to it for live search of new companies."
fi
grep -q '^CRUSTDATA_API_KEY=.\+' .env 2>/dev/null || warn "No CRUSTDATA_API_KEY in .env: recorded companies only (no live search)."

# 4. PDF renderer (optional): Node + Playwright Chromium ----------------------------------
if [ -z "${SKIP_PDF:-}" ]; then
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    if ! NODE_PATH="$(npm root -g)" node -e "require('playwright')" >/dev/null 2>&1; then
      say "Installing Playwright for the PDF report (one time)"
      npm install -g playwright >/dev/null 2>&1 || warn "npm install -g playwright failed (try with admin rights); PDF download disabled."
    fi
    NODE_PATH="$(npm root -g)" node -e "require('playwright')" >/dev/null 2>&1 && \
      { npx --yes playwright install chromium >/dev/null 2>&1 || warn "Chromium download failed; PDF download may not work."; }
  else
    warn "Node.js not found: the dashboard works, but the PDF download button needs Node (https://nodejs.org)."
  fi
fi

# 5. Quick self-check, then start -------------------------------------------------------
$VPY -c "import fastapi, uvicorn, httpx, pydantic, numpy" || { echo "Dependency check failed."; exit 1; }
say "Starting Proofroom on http://localhost:${PORT}/demo  (Ctrl+C to stop)"
( sleep 2
  url="http://localhost:${PORT}/demo"
  if command -v xdg-open >/dev/null 2>&1; then xdg-open "$url" >/dev/null 2>&1
  elif command -v open >/dev/null 2>&1; then open "$url"
  elif command -v start >/dev/null 2>&1; then start "$url"
  elif command -v cmd.exe >/dev/null 2>&1; then cmd.exe /c start "$url"
  fi ) >/dev/null 2>&1 &
exec $VPY -m uvicorn proofroom.web:app --host 127.0.0.1 --port "$PORT"
