#!/data/data/com.termux/files/usr/bin/bash
# Installer: NPU runtime + model + web UI for Xiaomi Pad 7 (SM7675 / Hexagon v73).
# Usage (from Termux):  su -c 'bash scripts/install.sh'
set -e

REPO="saksham-991/xiaomi-pad7-npu-llm"
DIR=/data/local/tmp/qwen-npu
MODEL_URL="https://huggingface.co/unsloth/Qwen3-1.7B-GGUF/resolve/main/Qwen3-1.7B-Q4_0.gguf"
MODEL_NAME="Qwen3-1.7B-Q4_0.gguf"

echo "[1/4] fetching latest NPU runtime release"
mkdir -p "$DIR"
TMP=$(mktemp -d)
API="https://api.github.com/repos/$REPO/releases"
URL=$(curl -sL "$API" | grep -o '"browser_download_url": *"[^"]*llama-cpp-hexagon-v73-android.tar.gz"' | head -1 | sed 's/.*"browser_download_url": *"//; s/"$//')
if [ -z "$URL" ]; then
  echo "no release asset found; build first: gh workflow run build-hexagon.yml" >&2
  exit 1
fi
curl -L "$URL" -o "$TMP/runtime.tar.gz"
tar -xzf "$TMP/runtime.tar.gz" -C "$DIR"
chmod 755 "$DIR/bin"/* 2>/dev/null || true
chmod 755 "$DIR/lib"/*.so 2>/dev/null || true
rm -rf "$TMP"

echo "[2/4] model: $MODEL_NAME (1.1 GB, Q4_0)"
mkdir -p "$DIR/models"
if [ ! -f "$DIR/models/$MODEL_NAME" ]; then
  curl -L "$MODEL_URL" -o "$DIR/models/$MODEL_NAME"
fi

echo "[3/4] installing app files"
ROOT_SRC="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$DIR/app" "$DIR/scripts"
cp -r "$ROOT_SRC/app"/* "$DIR/app/"
cp -r "$ROOT_SRC/scripts"/* "$DIR/scripts/"
chmod 755 "$DIR/scripts"/*.sh

echo "[4/4] done"
cat <<'EOF'

Run:
  su -c '/data/local/tmp/qwen-npu/scripts/start-npu.sh'      # llama-server on NPU (8090)
  bash /data/local/tmp/qwen-npu/scripts/start-ui.sh          # web UI (8088)

Open http://127.0.0.1:8088 in Chrome.
One-shot: su -c '/data/local/tmp/qwen-npu/scripts/ask.sh "question" 256'
EOF
