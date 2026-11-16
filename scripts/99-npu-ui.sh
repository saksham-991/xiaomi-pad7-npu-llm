#!/system/bin/sh
# Boot: start ONLY the interrupt-driven UI listener on :8088 (no model, no polling).
sleep 20
if pgrep -f "/data/data/com.termux/files/home/pad7-npu/app/server.py" | grep -qv $$; then
  exit 0
fi
setsid /data/data/com.termux/files/usr/bin/python3 /data/data/com.termux/files/home/pad7-npu/app/server.py \
  >> /data/local/tmp/qwen-npu/ui.log 2>&1 < /dev/null &
