#!/usr/bin/env bash
# Merge a HF LoRA checkpoint, convert to GGUF and quantize to Q4_0 (CPU is fine).
# Usage: export_gguf.sh <merged_hf_dir> <out.gguf>
set -euo pipefail
SRC="${1:?merged HF model dir}"
OUT="${2:?output gguf path}"
LLAMACPP="${LLAMACPP_DIR:-$HOME/llama.cpp}"

python3 -m venv "$HOME/.venv-gguf" 2>/dev/null || true
. "$HOME/.venv-gguf/bin/activate"
pip -q install --upgrade pip
pip -q install -r "$LLAMACPP/requirements.txt"

python3 "$LLAMACPP/convert_hf_to_gguf.py" "$SRC" --outtype f16 --outfile "$OUT.f16.gguf"
"$LLAMACPP/build/bin/llama-quantize" "$OUT.f16.gguf" "$OUT" Q4_0
rm -f "$OUT.f16.gguf"
echo "done: $OUT"
