# Distillation pipeline (teacher: Particle-1)

The goal: a domain-locked student — Qwen3-1.7B — trained on reasoning traces authored by
Particle-1 across exactly these domains:

coding · systems engineering · linux sysadmin · android app development ·
software engineering · maths · physics · english (technical)

## Layout

```
seeds/*.jsonl        hand-authored Particle-1 traces (chat format, JSONL)
build_dataset.py     validates seeds, de-dupes, splits train/valid, optional local-teacher expansion
train_kaggle.ipynb   QLoRA training on Kaggle free T4x2, merges + exports Q4_0 GGUF
export_gguf.sh       local conversion/quantization fallback
```

## JSONL schema

```json
{"domain":"math","messages":[{"role":"system","content":"..."},{"role":"user","content":"..."},{"role":"assistant","content":"..."}]}
```

## Steps

1. **Collect/author traces** into`seeds/`. Target 1k-3k examples; quality beats quantity.
2. **Build dataset**

   ```bash
   python3 build_dataset.py --out data
   ```

3. **Train** — upload `data/` + notebook to Kaggle, run with GPU T4x2.
   Settings: QLoRA r=16, alpha=32, lr=1e-4, 2-3 epochs, max_len 4096.
4. **Export** — notebook merges the adapter, converts to GGUF, quantizes Q4_0.
5. **Deploy** — copy the GGUF into `/data/local/tmp/qwen-npu/models/` and point
   `MODEL=` at it in `scripts/start-npu.sh`.

## Hard rules

- Q4_0 only. `ggml-hexagon` supports Q4_0 / Q8_0 / MXFP4 / FP32; Q4_K etc. will fall back to CPU.
- No CUDA-only ops, no custom kernels — the student must remain vanilla Qwen3 architecture.
- Keep English as the reasoning language; the teacher traces are all English.
