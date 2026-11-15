#!/system/bin/sh
# One-shot question to the NPU model (run as root).
DIR=/data/local/tmp/qwen-npu
cd "$DIR" || exit 1
export LD_LIBRARY_PATH="$DIR/lib:/vendor/lib64"
export ADSP_LIBRARY_PATH="$DIR/lib"
export GGML_HEXAGON_MM_SELECT=1
export GGML_HEXAGON_POWER_MODE="${GGML_HEXAGON_POWER_MODE:-sustained_high_performance}"
MODEL="${MODEL:-$DIR/models/Qwen3-1.7B-Q4_0.gguf}"
exec ./bin/llama-cli -m "$MODEL" --device HTP0 -ngl 99 -t 4 -fa off -c 4096 -st -p "$1" -n "${2:-256}"
