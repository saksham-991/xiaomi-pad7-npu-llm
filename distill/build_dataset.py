#!/usr/bin/env python3
"""Validate + split Particle-1 seed traces into train/valid JSONL."""
import argparse, glob, hashlib, json, os, random, re

DOMAINS = ["coding", "systems", "linux", "android", "swe", "math", "physics", "english", "scope", "expert"]

def norm(text):
    return re.sub(r"\s+", " ", text.strip().lower())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default=os.path.join(os.path.dirname(__file__), "seeds"))
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "data"))
    ap.add_argument("--valid-ratio", type=float, default=0.08)
    ap.add_argument("--min-assistant-chars", type=int, default=80)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    rows, seen, skipped = [], set(), 0
    for fp in sorted(glob.glob(os.path.join(args.seeds, "*.jsonl"))):
        for line in open(fp, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                ex = json.loads(line)
            except Exception as e:
                print(f"skip {os.path.basename(fp)}: {e}")
                skipped += 1
                continue
            msgs = ex.get("messages") or []
            if len(msgs) < 3:
                skipped += 1
                continue
            assistant = msgs[-1].get("content", "")
            if len(assistant) < args.min_assistant_chars:
                skipped += 1
                continue
            h = hashlib.sha1(norm(msgs[-2]["content"]).encode()).hexdigest()
            if h in seen:
                skipped += 1
                continue
            seen.add(h)
            rows.append({"messages": msgs, "domain": ex.get("domain", "general")})

    random.Random(1337).shuffle(rows)
    n_valid = max(1, int(len(rows) * args.valid_ratio)) if len(rows) > 10 else 0
    valid, train = rows[:n_valid], rows[n_valid:]

    def dump(path, data):
        with open(path, "w", encoding="utf-8") as f:
            for r in data:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

    dump(os.path.join(args.out, "train.jsonl"), train)
    dump(os.path.join(args.out, "valid.jsonl"), valid)

    per = {}
    for r in rows:
        per[r["domain"]] = per.get(r["domain"], 0) + 1
    print(f"total {len(rows)}  train {len(train)}  valid {len(valid)}  skipped {skipped}")
    for d in sorted(per):
        print(f"  {d:10s} {per[d]}")
    missing = [d for d in DOMAINS if d not in per]
    if missing:
        print("WARNING missing domains:", ", ".join(missing))

if __name__ == "__main__":
    main()
