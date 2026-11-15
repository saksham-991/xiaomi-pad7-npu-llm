#!/usr/bin/env python3
"""CPU LoRA training for LFM2-1.2B on Particle-1 seeds (no CUDA, no bnb)."""
import json, math, os, sys, time, random
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, PeftModel

MODEL = os.environ.get("BASE_MODEL", "LiquidAI/LFM2-1.2B")
DATA = os.environ.get("DATA", "distill/data/train.jsonl")
OUT = os.environ.get("OUT", "out")
MAXLEN = int(os.environ.get("MAXLEN", "768"))
EPOCHS = int(os.environ.get("EPOCHS", "2"))
LR = float(os.environ.get("LR", "1e-4"))
WORKERS = int(os.environ.get("WORKERS", "8"))

torch.set_num_threads(WORKERS)
random.seed(1337); torch.manual_seed(1337)

tok = AutoTokenizer.from_pretrained(MODEL, trust_remote_code=True)
if tok.pad_token is None:
    tok.pad_token = tok.eos_token

rows = [json.loads(l) for l in open(DATA) if l.strip()]
examples = []
for ex in rows:
    msgs = ex["messages"]
    prompt = tok.apply_chat_template(msgs[:-1], tokenize=False, add_generation_prompt=True)
    answer = msgs[-1]["content"] + (tok.eos_token or "")
    p = tok(prompt, add_special_tokens=False)["input_ids"]
    a = tok(answer, add_special_tokens=False)["input_ids"]
    ids = (p + a)[:MAXLEN]
    labels = ([-100] * len(p) + a)[:MAXLEN]
    if len(ids) > len(p) + 4:
        examples.append({"input_ids": ids, "labels": labels})
print(f"examples {len(examples)}  avg len {sum(len(e['input_ids']) for e in examples)/len(examples):.0f}", flush=True)


class DS(Dataset):
    def __init__(self, ex): self.ex = ex
    def __len__(self): return len(self.ex)
    def __getitem__(self, i): return self.ex[i]


def collate(batch):
    mx = max(len(b["input_ids"]) for b in batch)
    ids, labels, mask = [], [], []
    for b in batch:
        n = len(b["input_ids"]); pad = mx - n
        ids.append(b["input_ids"] + [tok.pad_token_id] * pad)
        labels.append(b["labels"] + [-100] * pad)
        mask.append([1] * n + [0] * pad)
    return {"input_ids": torch.tensor(ids), "labels": torch.tensor(labels), "attention_mask": torch.tensor(mask)}


print("loading model (fp32, CPU) ...", flush=True)
model = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float32, trust_remote_code=True)
model.gradient_checkpointing_enable()
model.enable_input_require_grads()
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.0, bias="none", task_type="CAUSAL_LM",
                  target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
model = get_peft_model(model, lora)
model.print_trainable_parameters()

dl = DataLoader(DS(examples), batch_size=1, shuffle=True, collate_fn=collate)
steps_per_epoch = math.ceil(len(examples))
total_steps = steps_per_epoch * EPOCHS
warmup = max(2, int(0.03 * total_steps))
opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=LR, weight_decay=0.0)
sched = torch.optim.lr_scheduler.LambdaLR(
    opt, lambda s: (s + 1) / max(1, warmup) if s < warmup else max(0.05, 1 - (s - warmup) / max(1, total_steps - warmup)))

model.train()
global_step = 0; t0 = time.time()
for ep in range(EPOCHS):
    for bi, batch in enumerate(dl):
        out = model(**batch)
        loss = out.loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad], 1.0)
        opt.step(); sched.step(); opt.zero_grad(set_to_none=True)
        global_step += 1
        if global_step % 5 == 0 or global_step == 1:
            print(f"ep {ep+1} step {global_step}/{total_steps} loss {loss.item():.4f} "
                  f"lr {sched.get_last_lr()[0]:.2e} {(time.time()-t0)/global_step:.1f}s/step", flush=True)

os.makedirs(OUT, exist_ok=True)
model.save_pretrained(os.path.join(OUT, "adapter"))
tok.save_pretrained(os.path.join(OUT, "adapter"))

print("merging adapter ...", flush=True)
base = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float16, trust_remote_code=True)
merged = PeftModel.from_pretrained(base, os.path.join(OUT, "adapter")).merge_and_unload()
merged.save_pretrained(os.path.join(OUT, "merged"), safe_serialization=True)
tok.save_pretrained(os.path.join(OUT, "merged"))
print("merged saved", flush=True)
