#!/data/data/com.termux/files/usr/bin/bash
# Start the web UI + proxy (Termux user, no root needed).
set -e
APP="$(cd "$(dirname "$0")/../app" && pwd)"
export LLAMA_BASE="${LLAMA_BASE:-http://127.0.0.1:8090}"
export APP_PORT="${APP_PORT:-8088}"
export CTX_SIZE="${CTX_SIZE:-4096}"
exec python3 "$APP/server.py"
