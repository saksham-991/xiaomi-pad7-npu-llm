# Shrinking the student (real MB cuts)

Distributed knowledge cannot be deleted per-topic. Size is reduced by one of:

1) Smaller base (main lever)
   - Qwen3-1.7B Q4_0 ~1.06 GB  (default; best accuracy)
   - Qwen3-0.6B Q4_0 ~0.40 GB  (distill the same seeds; evaluate before shipping)

2) Vocabulary pruning (after SFT)
   - Keep tokens covering code + English + technical symbols; drop rare CJK/emoji/etc.
   - Resize embed/lm_head, re-tokenize dataset, heal-finetune 1 epoch.
   - Typical saving: 100-150 MB on Qwen3-1.7B; also speeds up the embedding matmul.

3) Structured pruning + heal
   - Layer pruning: 28 -> 24 layers (~15% weights) then SFT heal.
   - Width/neuron pruning by low activation frequency on domain data, then SFT heal.
   - Aggressive; requires a GPU run and eval gate.

Evaluation gate: run distill/eval.py on held-out domain tasks; ship the smallest variant that
does not regress >2% vs the 1.7B baseline.
