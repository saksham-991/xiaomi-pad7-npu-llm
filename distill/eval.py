#!/usr/bin/env python3
"""Sanity eval gate: compare a candidate GGUF against expected answers via llama-server.

Usage:
  python3 eval.py --base http://127.0.0.1:8090 --cases eval_cases.jsonl
Each case: {"q": "...", "must": ["substr1","substr2"], "domain": "math"}
Exit code 0 if pass rate >= --min-pass (default 0.8).
"""
import argparse, json, urllib.request

def ask(base, q, n=512):
    body = json.dumps({
        "messages": [{"role": "user", "content": q}],
        "max_tokens": n, "temperature": 0.1,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode()
    req = urllib.request.Request(base + "/v1/chat/completions", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        d = json.loads(r.read())
    return d["choices"][0]["message"]["content"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8090")
    ap.add_argument("--cases", default="eval_cases.jsonl")
    ap.add_argument("--min-pass", type=float, default=0.8)
    a = ap.parse_args()
    cases = [json.loads(l) for l in open(a.cases) if l.strip()]
    passed = 0
    for c in cases:
        out = ask(a.base, c["q"])
        low = out.lower()
        ok = all(s.lower() in low for s in c["must"])
        passed += ok
        print(("PASS" if ok else "FAIL"), c.get("domain", ""), "|", c["q"][:60])
        if not ok:
            print("   got:", out[:200].replace("\n", " "))
    rate = passed / max(1, len(cases))
    print(f"\n{passed}/{len(cases)} = {rate:.2%} (min {a.min_pass:.0%})")
    raise SystemExit(0 if rate >= a.min_pass else 1)

if __name__ == "__main__":
    main()
