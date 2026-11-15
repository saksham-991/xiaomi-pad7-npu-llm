# Device engineering notes — Xiaomi Pad 7 (uke) / SM7675 / Hexagon v73

## Hardware

- SoC: Snapdragon 7+ Gen 3 (SM7675), Hexagon **v73**, 4x HVX, 1x HMX, 4 MB VTCM
- RAM: 8 GB (device reports 7.5 GB); Android uses ~5-6 GB, leaving ~1.6-2 GB free
- NPU access: FastRPC `/dev/adsprpc-smd`, vendor libs `/vendor/lib64/libQnnHtp*.so`,
  skel dir `/vendor/lib/rfsa/adsp`; unsigned PD (domain 3) works with the bundled
  `libggml-htp-v73.so`, no signing required

## Op-level failures found (and why previous attempts were gibberish)

`test-backend-ops -b HTP0` against the CPU reference:

- `MUL_MAT`: many shapes returned `inf` (HMX tiled kernels). HVX-only path
  (`GGML_HEXAGON_MM_SELECT=1`) passes **all 1856** cases.
- `FLASH_ATTN_EXT`: returns `inf` for every mask/kv config on v73. Disabled with `-fa off`;
  the model then computes attention as MUL_MAT + SOFTMAX + CPY on the NPU, which passes.

Result: coherent English/math answers instead of token soup.

## Performance (measured on-device)

| Model | pp (t/s) | tg (t/s) | backend | device |
| --- | --- | --- | --- | --- |
| Llama-3.2-1B Q4_0 | 82.3 | 32.3 | llama-bench | HTP0 |
| Qwen3-1.7B Q4_0 | 49-53 | 21-24 | llama-cli | HTP0 |

## RAM math

Weights are pinned in shared DDR through RPCMEM (not swappable):

- Qwen3-1.7B Q4_0: 1.06 GB weights; KV f16 ≈ 112 KiB/token (28 layers, 8 KV heads,
  head_dim 128) → 4K context ≈ 448 MiB; host buffers ~0.25 GB → **~1.5-1.7 GB peak**.
- Phi-4-mini 3.8B Q4_0: 2.33 GB weights; KV ≈ 96 KiB/token (32 layers, 8 KV heads,
  head_dim 96) → 4K ≈ 384 MiB → **~2.9 GB pinned**. With ~1.6 GB free this OOMs; observed
  system crash. Hence 1.7B student.

Batch sizes `-b 256 -ub 256` and `-np 1` keep compute buffers and KV slots small.

## NPU session window

Each FastRPC session has ~3.5 GB of 32-bit VA space. The backend dynamically maps/unmaps
weight buffers per batch. Staying under ~2.5 GB total (weights + KV + compute) avoids
mapping pressure on v73.

## Runtime env (mandatory)

```
LD_LIBRARY_PATH=/data/local/tmp/qwen-npu/lib:/vendor/lib64
ADSP_LIBRARY_PATH=/data/local/tmp/qwen-npu/lib
GGML_HEXAGON_MM_SELECT=1
GGML_HEXAGON_POWER_MODE=sustained_high_performance
llama-server ... --device HTP0 -ngl 99 -t 4 -fa off -c 4096 -b 256 -ub 256 -np 1 --jinja
```

`--device HTP0` pins all tensor ops to the Hexagon; OpenCL/GPU and CPU tensor math are
never selected.

## Search

DuckDuckGo lite HTML is fetched server-side (keyless, no tracking JS) and parsed for the
top 5 titles/snippets/URLs; results are injected as a dated system message and cited by
the model.

## Context compaction at 85%

Trigger: tokenized conversation > 0.85 × 4096. The same NPU model is called with a
compaction system prompt (lossless bullets: paths, commands, versions, errors, symptoms,
root causes, fixes, decisions, open questions, latest state). The chat history is replaced
by `[summary] + last user message`; the UI exposes the summary. This keeps effective
context unbounded at constant KV size.

## Gotchas

- Missing `ADSP_LIBRARY_PATH` → skel load fails, backend won't start.
- Q4_K/Q5_K GGUFs fall back to CPU; use Q4_0 only.
- Chrome can reach Termux loopback servers directly (`127.0.0.1`).
- The UI/proxy is stdlib-only Python; no pip installs on device.
