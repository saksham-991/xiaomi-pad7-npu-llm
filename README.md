# Pad7 NPU LLM — local AI on the Hexagon NPU

Local chat stack for the **Xiaomi Pad 7 (Snapdragon 7+ Gen 3 / SM7675, Hexagon v73)**.
Inference runs on the **NPU only** (`--device HTP0 -ngl 99`), with no GPU or CPU layer offload.

Default model: **Qwen3-1.7B Q4_0**, 8192 context, real thinking toggle.
Other `Q4_0` GGUFs in the models folder are selectable at runtime.

## Features

- NPU-only inference (`llama.cpp` + `ggml-hexagon`, pinned build)
- Chat UI: AMOLED/light themes, streaming, reasoning panel, sessions/history
- **Model picker** in the header: lists every GGUF in `/data/local/tmp/qwen-npu/models`, with ✓ on the active one; switching keeps the same chat
- **Thinking toggle** (Qwen3 `enable_thinking`): fast answers or chain-of-thought
- **On-demand loading**: the model starts when a chat page connects and is unloaded when the page closes (plus a 90 s idle timeout)
- **Live health dot**: 1 s polling; red when the engine is down
- Keyless web search (Bing/DDG via reader proxy) with deep page excerpts
- Auto context compaction at 85%: lossless bullet summary, then continues
- IDE-style code blocks with syntax colours and per-block copy
- Separate **Pad7 SysMon** companion app (CPU/GPU/RAM/zram/disk/net/DSP + process lists)

## Run

The UI server (light, no model) and the engine are separate:

```bash
# UI server on :8088 (safe to keep running; ~30 MB)
bash scripts/start-ui.sh

# open http://127.0.0.1:8088
# -> the page starts llama-server on the NPU automatically
# -> closing the tab stops it and frees RAM
```

Manual engine control:

```bash
curl -X POST http://127.0.0.1:8088/api/engine/start
curl -X POST http://127.0.0.1:8088/api/engine/stop
curl http://127.0.0.1:8088/api/health     # {"llama":true,"ctx":8192,"model":"..."}
```

There is no boot autostart: nothing loads until you open the chat.

## Models

Drop any compatible GGUF into `/data/local/tmp/qwen-npu/models/` and pick it in the header.

- Quantization: **Q4_0** (also Q8_0 / MXFP4 / FP32). Q4_K/Q5_K would fall back to CPU — not supported here.
- Architecture must be supported by the pinned llama.cpp build and include a chat template.
- RAM: weights + KV must stay within ~2 GB pinned. At 8K context Qwen3-1.7B uses ~1.5–1.8 GB.
- The selected model is remembered in `models/selected`.

## NPU flags (do not change)

```
GGML_HEXAGON_MM_SELECT=1   # HMX matmul kernels return inf on v73
-fa off                    # flash-attention returns inf on v73
--device HTP0 -ngl 99
```

With these, all 1856 MUL_MAT and 358 norm/rope/softmax/glu backend tests pass and output matches CPU at temperature 0.

## Layout

```
app/                  chat UI + proxy, search, summarizer, engine lifecycle API
scripts/              install, start-ui, start-npu, ask
android/              fullscreen wrapper sources (not required for the web UI)
android/sysmon/       Pad7 SysMon app sources
sysmon/sysmon.sh      root sampler for SysMon
distill/              trace datasets, generators, training and GGUF export
.github/workflows/    APK builds and CPU LoRA training
```

## SysMon

Rooted companion app: overview donuts (CPU/memory/GPU), per-core bars, memory/zram,
disk, network throughput, DSP/NPU state and FastRPC session counts, sortable process lists,
poll interval 1/2/5/10 s. Note: the kernel does not expose HTP utilization %, so NPU
activity is shown via DSP state, session counts and the LLM engine status.

## Troubleshooting

- Engine stays red: `su -c 'cat /data/local/tmp/qwen-npu/server.log'`; ensure KernelSU root is granted and the selected model file exists.
- Speed degraded: close other heavy apps — RAM pressure evicts the pinned NPU weights.
- UI not updating: hard-reload the page (assets are versioned).

MIT licensed.
