# Xiaomi Pad 7 — Pure-NPU Local LLM (Qwen3-1.7B + Web Chat)

Runs a local LLM **entirely on the Qualcomm Hexagon NPU (HTP v73)** of the Xiaomi Pad 7
(Snapdragon 7+ Gen 3 / SM7675). No GPU compute, no CPU tensor fallback, no cloud.

Default model: **LFM2-1.2B Q4_0** (0.66 GB) at **16K context** — chosen by on-device bake-off
below. Optional accuracy profile: Qwen3-1.7B (thinking mode).

- NPU-only inference via `llama.cpp` + `ggml-hexagon`
- Web chat UI: Material You dark theme, history, streaming, live reasoning panel, thinking animation
- `search ...` performs a real web search (DuckDuckGo, keyless) and feeds results into context
- Auto context compaction at **85%**: lossless bullet summary, then the chat continues seamlessly
- ~1.1 GB model, ~1.5 GB peak RAM at 4K context — safe on an 8 GB tablet
- Reproducible: pinned llama.cpp commit, GitHub Actions cross-build, install script

## Model bake-off (all measured on this NPU, 6 expert probes)

| Model | Size | Score | Gen t/s | Verdict |
| --- | --- | --- | --- | --- |
| **LFM2-1.2B Q4_0** | 0.66 GB | **5.0/6** | 32-41 | **Default** |
| Qwen3-1.7B Q4_0 | 1.06 GB | 4.5/6 | 19-23 | Optional thinking profile |
| Qwen2.5-1.5B Q4_0 | 0.89 GB | 3.5/6 | 20-27 | Unsafe `find|rm` answer |
| Qwen3-0.6B Q4_0 | 0.38 GB | 3.0/6 | 31-37 | Weak reasoning |
| Gemma3-1B Q4_0 | 0.67 GB | 2.0/6 | 27-30 | Template issues |
| SmolLM2-1.7B Q4_0 | 0.93 GB | 1.5/6 | 15-18 | Wrong math, slowest |
| Llama-3.2-1B Q4_0 | 0.74 GB | 0.5/6 | 30-34 | Failed prompts |

LFM2 at 8K context: 75.6 t/s prompt, 35.6 t/s generation, RAM stable.

## Why Phi-4-mini 3.8B is not used

Phi-4-mini Q4_0 is 2.33 GB of **pinned, unswappable** NPU weights plus KV. On this tablet
only ~0.8-2 GB is available while Android runs, and two controlled attempts (with watchdog,
context reduced to 1024, batch 64) caused Android system_server death (Bluetooth stack
restart) before the allocation succeeded. It cannot run here without pruning it into a
different, smaller model. The 1.2B student is the operating envelope; the `distill/`
pipeline trains it on Particle-1-authored expert traces (coding, systems, Linux, Android,
SWE, maths, physics, technical English) to raise domain density.

## NPU correctness on SM7675 (v73) — the anti-gibberish flags

Two backend kernels are broken on Hexagon v73 and return `inf` (verified with
`test-backend-ops`):

| Kernel | Status on v73 | Fix (mandatory) |
| --- | --- | --- |
| HMX `MUL_MAT` | produces `inf` | `GGML_HEXAGON_MM_SELECT=1` (HVX path, still NPU) |
| `FLASH_ATTN_EXT` | produces `inf` | `-fa off` (attention via MUL_MAT+SOFTMAX on NPU) |

With both applied, all 1856 MUL_MAT and 358 norm/rope/softmax/glu op tests pass and the
model produces coherent answers.

## Quick start

```bash
# 1) install runtime + model + app (root)
su -c 'bash scripts/install.sh'

# 2) start the NPU runtime
su -c '/data/local/tmp/qwen-npu/scripts/start-npu.sh'

# 3) start the web UI (Termux user)
bash /data/local/tmp/qwen-npu/scripts/start-ui.sh

# open http://127.0.0.1:8088 in Chrome
```

One-shot CLI:

```bash
su -c '/data/local/tmp/qwen-npu/scripts/ask.sh "Explain HMX vs HVX" 256'
```

## Build it yourself

The runtime is built in CI, not on the tablet:

1. `Actions -> build-hexagon-v73 -> Run workflow`
2. Artifact: `llama-cpp-hexagon-v73-android.tar.gz` (release `npu-b*`)

Pinned: `llama.cpp @ b54752df40e4d8e53d34ef5a598336b4e4871d39`, Hexagon SDK toolchain
`ghcr.io/snapdragon-toolchain/arm64-android:v0.8`, preset
`arm64-android-snapdragon-release`, `--hex-arch v73`.

## Search

Type `search <query>` or toggle the **Search** chip. The app fetches DuckDuckGo lite
results (no API key) and injects them as a system block with retrieval timestamp.

## Context compaction

When usage crosses 85% of the 4096-token window, the server asks the same NPU model for a
**lossless bullet summary** (all paths, flags, errors, symptoms, decisions, open questions,
latest state), replaces the history with that summary + the newest message, and the
conversation continues. The UI shows a "Context compacted" chip with the full summary.

## Distillation (student: LFM2-1.2B)

Training priorities, in order: **physics, sysadmin, systems engineering, coding, maths**.
Style target: reason when needed, shortest correct solution, no over-engineering.
Teacher traces are authored by Particle-1 (`distill/seeds/`), 65 examples currently,
schema-checked and split by `distill/build_dataset.py`.

Training runs on Kaggle free T4x2 with `distill/train_kaggle.ipynb` (QLoRA r=16, 2 epochs),
then exports Q4_0 GGUF and drops straight into `/data/local/tmp/qwen-npu/models/`.

## Layout

```
app/                   web UI + stdlib proxy/search/summarizer
scripts/               install, NPU server, UI launcher, one-shot ask
distill/               Particle-1 seed traces, dataset builder, Kaggle QLoRA notebook, GGUF export
docs/DEVICE_NOTES.md   engineering log (bugs, measurements, RAM math)
.github/workflows/     pinned cross-compile + release
```

## Limits

- Q4_0 / Q8_0 / MXFP4 / FP32 only (ggml-hexagon); do not use Q4_K/Q5_K.
- 4K context committed; the summarizer extends effective context at constant RAM.
- FastRPC requires root (`su`); the web UI itself runs unprivileged.
- Hexagon v73: keep `GGML_HEXAGON_MM_SELECT=1` and `-fa off`.

MIT licensed.
