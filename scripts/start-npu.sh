#!/system/bin/sh
# Start llama-server on the Hexagon NPU (HTP v73). Run as root.
set -e
DIR=/data/local/tmp/qwen-npu
cd "$DIR" || exit 1

export LD_LIBRARY_PATH="$DIR/lib:/vendor/lib64"
export ADSP_LIBRARY_PATH="$DIR/lib"
# REQUIRED on SM7675 / Hexagon v73: HMX matmul kernels return inf (gibberish).
export GGML_HEXAGON_MM_SELECT=1
# REQUIRED: flash-attn kernels return inf on v73.
export GGML_HEXAGON_POWER_MODE="${GGML_HEXAGON_POWER_MODE:-sustained_high_performance}"

SEL=$(cat "$DIR/models/selected" 2>/dev/null)
if [ -n "$SEL" ] && [ -f "$DIR/models/$SEL" ]; then
  MODEL="$DIR/models/$SEL"
else
  MODEL="${MODEL:-$DIR/models/model.gguf}"
fi
if [ ! -f "$MODEL" ]; then MODEL="$DIR/models/model.gguf"; fi
CTX="${CTX:-8192}"

exec ./bin/llama-server \
  -m "$MODEL" \
  --device HTP0 -ngl 99 \
  -t 4 -fa off -c "$CTX" -b 256 -ub 256 -np 1 \
  --host 127.0.0.1 --port 8090 \
  --jinja --reasoning-format deepseek \
  --no-webui
