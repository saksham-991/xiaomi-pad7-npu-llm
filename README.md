# Xiaomi Pad 7 — Pure-NPU Local LLM (Qwen/LFM2 + Chat UI + APK wrapper)

Runs a local LLM **entirely on the Qualcomm Hexagon NPU (HTP v73)** of the
Xiaomi Pad 7 (Snapdragon 7+ Gen 3 / SM7675). No GPU compute, no CPU tensor
fallback, no cloud. Ships as a Termux stack and a fullscreen WebView APK wrapper.

| | |
|---|---|
| Model (default) | LFM2-1.2B Q4_0 — 0.66 GB |
| Context | 16 384 tokens (full-speed; 32K runs but ~5 t/s) |
| Speed (measured) | ~76 t/s prompt, ~35–43 t/s generation |
| Memory | ~1.1–1.5 GB peak, safe on 8 GB |
| Backend | llama.cpp @ `b54752df40e4d8e53d34ef5a598336b4e4871d39`, ggml-hexagon |
| Device | HTP0 only (`--device HTP0 -ngl 99`) |

## Two ways to run

### A. Termux stack (works today)

```bash
su -c '/data/local/tmp/qwen-npu/scripts/start-npu.sh > /data/local/tmp/qwen-npu/server.log 2>&1 &'
cd /data/data/com.termux/files/home/pad7-npu/app && python3 server.py
# open http://127.0.0.1:8088
```

One-shot:

```bash
su -c '/data/local/tmp/qwen-npu/scripts/ask.sh "What is 15% of 240?" 128'
```

### B. Fullscreen APK wrapper

`build-apk.yml` builds a ~5.6 MB WebView shell that, on launch, starts the NPU
server + Python UI as detached root processes and goes fullscreen to
`http://127.0.0.1:8088`. Requires KernelSU/Magisk root once. Signing keystore is
stable across builds (stored as the `signing` release asset), so updates keep
data and the model.

### Autostart at boot

```bash
su -c 'cp scripts/99-npu-llm.sh /data/adb/service.d/ && chmod 755 /data/adb/service.d/99-npu-llm.sh'
```

## NPU correctness on SM7675 (v73) — the anti-gibberish flags

`test-backend-ops` proves two kernels are broken on Hexagon v73 (return `inf`):

| Kernel | Fix (mandatory) |
| --- | --- |
| HMX `MUL_MAT` | `GGML_HEXAGON_MM_SELECT=1` (HVX path, still NPU) |
| `FLASH_ATTN_EXT` | `-fa off` (attention via MUL_MAT+SOFTMAX on NPU) |

With both: all 1856 MUL_MAT and 358 norm/rope/softmax/glu tests pass, and the
model produces coherent output. NPU output was verified **token-identical to
CPU** at temperature 0 on both LFM2 and LFM2.5 — the backend is numerically
faithful; wrong answers were model/quant quality, not corruption.

## Chat features

- AMOLED-black + light themes (auto/dark/light toggle), Material-3-inspired UI
- Streaming tokens, live reasoning panel, thinking animation
- ChatGPT-style sessions/history (localStorage), export/import
- `search ...` or Search chip → keyless web search (Jina→DDG, DDG IA, Wikipedia fallback)
- IDE-style code blocks: language label, syntax colors, per-block Copy
- Auto context compaction at **85%**: lossless bullet summary (paths, commands,
  errors, decisions, latest state), history replaced, conversation continues
- Neutral assistant system prompt; sampling temp 0.4, top_p 0.9, repeat_penalty 1.12

## Model bake-off (on-device, 6 expert probes)

| Model | Size | Score | Gen t/s |
| --- | --- | --- | --- |
| **LFM2-1.2B Q4_0** | 0.66 GB | **5.0/6** | 32–41 |
| Qwen3-1.7B Q4_0 | 1.06 GB | 4.5/6 | 19–23 |
| Qwen2.5-1.5B Q4_0 | 0.89 GB | 3.5/6 | 20–27 |
| Qwen3-0.6B Q4_0 | 0.38 GB | 3.0/6 | 31–37 |
| Gemma3-1B Q4_0 | 0.67 GB | 2.0/6 | 27–30 |
| SmolLM2-1.7B Q4_0 | 0.93 GB | 1.5/6 | 15–18 |
| Llama-3.2-1B Q4_0 | 0.74 GB | 0.5/6 | 30–34 |

LFM2.5-1.2B variants failed basic arithmetic (15% of 240 → "240"/"360") on both
NPU and CPU → rejected.

## Why Phi-4-mini 3.8B is not used

2.33 GB of pinned, unswappable NPU weights + KV. With Android running, available
RAM is ~0.8–2 GB; two controlled attempts (watchdog, 1K ctx, batch 64) caused
Android system_server death (Bluetooth restart) before allocation succeeded. It
cannot run here without pruning it into a different model.

## Distillation pipeline (Particle-1 authored traces)

`distill/` contains:
- `seeds/` — hand-authored expert traces (physics, sysadmin, systems, coding, math, SWE, Android, English)
- `generate_pollinations.py` — autonomous trace expansion (keyless gpt-oss-20b)
- `build_dataset.py` — validate/dedupe/split
- `train_cpu.py` + `train-lfm2.yml` — CPU LoRA (r=32, 3 epochs, lr 5e-5) with GGUF export
- `train_lfm2_kaggle.ipynb` — T4 QLoRA alternative
- `eval.py` + `eval_cases.jsonl` — pass/fail gate before deploying a distilled model

Current status: an r=16/60-example LoRA run completed but **failed the eval gate**
(no command-accuracy gain vs base, some regressions), so it is not shipped.
The app remains on base LFM2-1.2B until a distilled candidate wins the gate.

## Layout

```
app/                    web UI + stdlib proxy/search/85% summarizer
scripts/                install, NPU server, UI launcher, one-shot ask, boot autostart
android/                fullscreen WebView wrapper APK
distill/                traces, generators, training, eval, GGUF export
docs/DEVICE_NOTES.md    engineering log (bugs, measurements, RAM math)
.github/workflows/      build-apk (wrapper), build-hexagon (runtime), train-lfm2 (CPU LoRA)
```

## Using a different model (drop-in)

The server model is just a path, so any GGUF that satisfies the NPU backend works:

1. Copy it to `/data/local/tmp/qwen-npu/models/model.gguf` (this path is preferred automatically), or
   set `MODEL=/path/to/file.gguf` when running `start-npu.sh`.
2. Restart the backend (close/reopen the wrapper, or `pkill -f llama-server` then start again).

Requirements:
- Quantization: **Q4_0**, Q8_0, MXFP4 or FP32 (Q4_K/Q5_K fall back to CPU — not allowed here).
- Architecture supported by pinned llama.cpp `b54752d` and chat template present (`--jinja`).
- Fits the budget: weights + KV ≤ ~2 GB pinned (up to ~2B Q4_0 with 16K context).
- Hexagon v73 flags stay: `GGML_HEXAGON_MM_SELECT=1`, `-fa off`, `--device HTP0 -ngl 99`.

The web UI/wrapper are model-agnostic; only the chip label is cosmetic.

## Troubleshooting

- **Gibberish** → keep `GGML_HEXAGON_MM_SELECT=1` and `-fa off`.
- **Model answers with invented commands** → use the neutral system prompt in
  `app/server.py`; start a new chat (old hallucinated turns bias the model).
- **Wrapper shows splash forever** → backend not up yet; reopen after boot
  autostart, or run the Termux commands above.
- **APK update wipes data** → only happens across signing-key changes; the stable
  key is now stored in the `signing` release, so future updates keep data.
- **Pushing a GGUF into app storage** (optional): must be owned by the app UID
  and carry its SELinux categories, e.g.
  `chown -R $(stat -c %u /data/data/com.pad7.npuchat) ... && chcon -R "$(ls -Zd /data/data/com.pad7.npuchat | awk '{print $1}')" ...`
- Q4_0 / Q8_0 / MXFP4 / FP32 only — Q4_K/Q5_K fall back to CPU.

MIT licensed.
