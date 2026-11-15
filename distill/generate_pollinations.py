#!/usr/bin/env python3
"""Autonomous trace generator: curated domain prompts -> gpt-oss-20b (keyless).

Produces JSONL SFT data for LFM2-1.2B. Resumable, rate-limit aware.
Usage: python3 generate_pollinations.py --target 400 --out distill/seeds/generated.jsonl
"""
import argparse, json, os, random, re, sys, time
import urllib.request, urllib.error, urllib.parse

ENDPOINT = "https://text.pollinations.ai/openai"
MODEL = "openai-fast"  # gpt-oss-20b reasoning

SYSTEM = ("You are a senior engineer and physicist. Answer technical questions with exact commands, "
          "paths, versions and numbers. Show only the necessary reasoning, then the direct answer. "
          "No filler, no over-engineering, no generic assistant phrases. English only.")

DOMAINS = {
"linux": [
 "find which process is holding a deleted file that keeps disk space used",
 "unit fails with status=203/EXEC, diagnose in order",
 "cap a service's memory with cgroup v2 MemoryHigh vs MemoryMax",
 "debug high iowait with no obvious disk throughput",
 "ssh key auth fails although the key is correct; check permissions and logs",
 "listening ports and the owning process, without netstat",
 "systemd timer vs cron for a job that must run after suspend",
 "ext4 filesystem full but du shows little usage",
 "safe way to process filenames with spaces in bash",
 "why load average is high while CPU idle",
 "OOM killer picks postgres; reduce risk without buying RAM",
 "debug DNS resolution failures inside a container",
 "rotate logs for a custom daemon with logrotate",
 "find files modified in the last 10 minutes",
 "check whether a disk is failing before it dies",
 "set up a read-only bind mount for a service",
 "why does `rm` not free space on NFS",
 "limit CPU and IO for a build process",
 "diagnose packet loss to one host only",
 "safe rsync backup with deletion protection",
],
"systems": [
 "explain context switch vs mode switch latency",
 "why does RSS overcount memory usage; PSS vs RSS",
 "priority inversion and priority inheritance in real kernels",
 "write() partial writes on sockets vs files; correct loop",
 "mmap succeeds but access gives SIGBUS",
 "false sharing and how padding fixes it",
 "why is a mutex not enough for publishing data to another thread",
 "NUMA effects on a threaded server",
 "epoll level-triggered vs edge-triggered pitfalls",
 "page cache behavior and drop_caches",
 "why does a 32-bit address space limit an NPU session",
 "branch predictor impact on tight loops",
 "compare futex and spinlock under contention",
 "what happens during a TCP close in both directions",
 "design a bounded queue with backpressure",
 "why is fsync slow and when is it required",
 "timeouts and retries: avoid retry storms",
 "how to measure tail latency correctly",
 "copy-on-write fork cost and how to avoid it",
 "memory-mapped IO vs DMA for large transfers",
],
"coding": [
 "python read dict with default without KeyError",
 "remove all occurrences of a value from a list preserving order",
 "why does popping while iterating skip elements",
 "C++ return pointer to local buffer crash",
 "Kotlin coroutine blocks UI thread; fix dispatcher",
 "SQL second highest salary per department with ties",
 "Rust borrow error returning a slice of a local String",
 "bash find files safely with spaces",
 "minimal Android foreground service for BLE scan API 34",
 "Compose LazyColumn recomposition storm fixes",
 "Python HTTP server without framework",
 "write a retry with exponential backoff and jitter",
 "binary search off-by-one pitfalls",
 "why is my regex catastrophic backtracking",
 "C++ RAII for a file descriptor",
 "Kotlin sealed class for API result states",
 "JSON parsing errors: validate schema first",
 "unit test vs integration test for a parser",
 "make a Python CLI with argparse subcommands",
 "SQL index that actually helps a range query",
],
"math": [
 "15% of 240",
 "solve 2^(x+1)-2^x=16",
 "minimum of x^2 ln x for x>0",
 "probability red then blue without replacement 3 red 5 blue",
 "derivative of x ln x and its integral",
 "sum of first n odd numbers proof",
 "inverse of a 2x2 matrix with numbers",
 "solve a system of two linear equations",
 "compound interest 1000 at 5% for 3 years",
 "expected value of a fair die",
 "area under y=x^2 from 0 to 3",
 "binomial probability n=5 p=0.5 exactly 2 successes",
 "simplify log expressions",
 "find gcd and lcm of two numbers",
 "convert repeating decimal to fraction",
 "prove sqrt(2) is irrational sketch",
 "limits: (1+1/n)^n intuition",
 "vector dot and cross product example",
 "standard deviation of a small dataset",
 "optimize area of a rectangle with fixed perimeter",
],
"physics": [
 "2 kg falls 5 m from rest, speed at impact",
 "electric field 0.10 m from 5 nC point charge",
 "isothermal expansion work for 0.5 mol at 300K from 1L to 3L",
 "why a spinning wheel resists falling, with formula",
 "projectile range at 45 degrees",
 "resonance frequency of an LC circuit",
 "why NPUs save energy for matmul, formula",
 "heat conduction through a wall",
 "Doppler shift for a moving source",
 "photoelectric effect threshold frequency",
 "moment of inertia of a hoop vs disk",
 "buoyancy of a submerged block",
 "series vs parallel resistors",
 "Snell's law refraction example",
 "half-life decay after 3 half lives",
 "centripetal force for a car on a curve",
 "work done by friction on an incline",
 "RMS speed of gas molecules",
 "magnetic force on a wire",
 "energy stored in a capacitor",
],
"sysadmin": [
 "check systemd service logs quickly",
 "verify which unit started a process",
 "find why a port is in use",
 "grant a user sudo only for one command",
 "set persistent ulimit for a service",
 "monitor disk IO per process",
 "restart a service only if config test passes",
 "find largest directories without hanging",
 "check kernel OOM kills history",
 "configure journald size limits",
 "test DNS with dig against a specific server",
 "why does SSH disconnect after idle; fix keepalive",
 "create a swapfile and enable it",
 "debug permissions denied on a directory",
 "check if a reboot is required after updates",
 "set up nftables to allow only SSH and HTTPS",
 "explain sticky bit on shared directories",
 "find world-writable files",
 "list systemd timers and next run",
 "lock down a service with systemd hardening",
],
}

USER_SUFFIXES = ["", " Be brief.", " Give exact commands.", " Include the key numbers.", " One short answer."]

def ask(prompt, timeout=300):
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 700,
        "temperature": 0.4,
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read())
        out = d["choices"][0]["message"]["content"].strip()
        if out:
            return out
    except Exception:
        pass
    # fallback: plain GET endpoint
    q = urllib.parse.quote(prompt)
    req2 = urllib.request.Request(f"https://text.pollinations.ai/{q}?model=openai-fast",
                                  headers={"User-Agent": "curl/8.23.0"})
    with urllib.request.urlopen(req2, timeout=timeout) as r:
        return r.read().decode("utf-8", "ignore").strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=400)
    ap.add_argument("--out", default="distill/seeds/generated.jsonl")
    ap.add_argument("--delay", type=float, default=3.0)
    ap.add_argument("--resume", action="store_true", default=True)
    a = ap.parse_args()

    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    done = 0
    if os.path.exists(a.out):
        done = sum(1 for _ in open(a.out))
    print(f"resume: {done} existing", flush=True)

    queue = [(d, p) for d, ps in DOMAINS.items() for p in ps]
    random.Random(7).shuffle(queue)
    seen = set()
    if os.path.exists(a.out):
        for line in open(a.out):
            try:
                seen.add(json.loads(line)["messages"][1]["content"])
            except Exception:
                pass

    with open(a.out, "a", encoding="utf-8") as f:
        n = done
        for dom, prompt in queue:
            if n >= a.target:
                break
            variant = prompt + random.choice(USER_SUFFIXES)
            if variant in seen:
                continue
            for attempt in range(5):
                try:
                    ans = ask(variant)
                    if len(ans) < 80:
                        raise ValueError("short answer")
                    rec = {"domain": dom, "messages": [
                        {"role": "system", "content": SYSTEM},
                        {"role": "user", "content": variant},
                        {"role": "assistant", "content": ans},
                    ]}
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    n += 1
                    print(f"[{n}/{a.target}] {dom}: {variant[:60]}", flush=True)
                    break
                except Exception as e:
                    print(f"retry {attempt+1}: {e}", file=sys.stderr, flush=True)
                    time.sleep(8 * (attempt + 1))
            time.sleep(a.delay)
    print("done", n, flush=True)

if __name__ == "__main__":
    main()
