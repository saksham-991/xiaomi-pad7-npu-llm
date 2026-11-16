#!/system/bin/sh
# Xiaomi Pad 7 pure-NPU LLM autostart (KernelSU / Magisk service.d)
# Install: su -c 'cp scripts/99-npu-llm.sh /data/adb/service.d/ && chmod 755 /data/adb/service.d/99-npu-llm.sh'
sleep 20
/data/local/tmp/qwen-npu/scripts/supervisor.sh >> /data/local/tmp/qwen-npu/supervisor.log 2>&1 &
