#!/system/bin/sh
# NPU LLM supervisor: keeps exactly one llama-server and one UI server alive.
# Runs as root from /data/adb/service.d at boot; also start manually if needed.
DIR=/data/local/tmp/qwen-npu
SELF=/data/local/tmp/qwen-npu/supervisor.pid
LOG=/data/local/tmp/qwen-npu/supervisor.log

mkdir -p "$DIR"

# single supervisor (stale pid-safe)
if [ -f "$SELF" ]; then
  OLD=$(cat "$SELF" 2>/dev/null)
  if [ -n "$OLD" ] && [ -d "/proc/$OLD" ]; then
    # is it really our supervisor?
    if tr '\0' ' ' < "/proc/$OLD/cmdline" 2>/dev/null | grep -q "supervisor.sh"; then
      exit 0
    fi
  fi
fi
echo $$ > "$SELF"

start_llama() {
  if ! pgrep -x llama-server >/dev/null 2>&1; then
    echo "$(date) starting llama-server" >> "$LOG"
    ( cd "$DIR" && ./scripts/start-npu.sh >> "$DIR/server.log" 2>&1 & )
  fi
}

start_ui() {
  if ! pgrep -f "pad7-npu/app/server.py" >/dev/null 2>&1; then
    echo "$(date) starting ui server" >> "$LOG"
    ( CDPATH= cd /data/data/com.termux/files/home/pad7-npu/app 2>/dev/null && \
      /data/data/com.termux/files/usr/bin/python3 /data/data/com.termux/files/home/pad7-npu/app/server.py >> "$DIR/ui.log" 2>&1 & )
  fi
}

trap 'rm -f "$SELF"' EXIT

while true; do
  start_llama
  start_ui
  sleep 2
done
