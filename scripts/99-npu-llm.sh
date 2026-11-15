#!/system/bin/sh
# Xiaomi Pad 7 pure-NPU LLM autostart (KernelSU / Magisk service.d)
# Install: su -c 'cp scripts/99-npu-llm.sh /data/adb/service.d/ && chmod 755 /data/adb/service.d/99-npu-llm.sh'
( sleep 25
  /data/local/tmp/qwen-npu/scripts/start-npu.sh >> /data/local/tmp/qwen-npu/server.log 2>&1 &
) &
( sleep 30
  /data/data/com.termux/files/usr/bin/python3 /data/data/com.termux/files/home/pad7-npu/app/server.py >> /data/local/tmp/qwen-npu/ui.log 2>&1 &
) &
