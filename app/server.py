#!/usr/bin/env python3
"""
Xiaomi Pad 7 pure-NPU LLM web app backend (stdlib only).

- Serves the Material You chat UI
- Proxies streaming chat to llama-server (Hexagon NPU)
- "search ..." -> DuckDuckGo lite results injected into context
- At 85% context usage -> lossless bullet summary, history replaced, chat continues
"""
import base64
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
STATIC = os.path.join(HERE, "static")

LLAMA = os.environ.get("LLAMA_BASE", "http://127.0.0.1:8090")
APP_PORT = int(os.environ.get("APP_PORT", "8088"))
CTX = int(os.environ.get("CTX_SIZE", "16384"))
SUMMARY_RATIO = float(os.environ.get("SUMMARY_RATIO", "0.85"))
SUMMARY_MAX_TOKENS = int(os.environ.get("SUMMARY_MAX_TOKENS", "700"))
UA = "Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Mobile Safari/537.36"

SYSTEM_PROMPT = (
    "You are a helpful local assistant running on the tablet's NPU. Answer naturally, briefly and "
    "accurately. For technical questions give exact commands and numbers. Never invent commands."
)


def jreq(url, payload=None, headers=None, timeout=600):
    data = None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    if payload is not None:
        data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers=hdrs, method="POST" if data else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def llama_json(path, payload=None, timeout=600):
    return json.loads(jreq(LLAMA + path, payload, timeout=timeout))


def llama_health():
    try:
        with urllib.request.urlopen(LLAMA + "/health", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def count_tokens(text):
    try:
        r = llama_json("/tokenize", {"content": text}, timeout=60)
        return len(r.get("tokens", []))
    except Exception:
        return max(1, int(len(text) / 3.5))


def _strip_md(s):
    s = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"<[^>]+>", "", s)
    s = s.replace("**", "").replace("&amp;", "&")
    return s.strip()


def _jina(url, timeout=60):
    req = urllib.request.Request(
        "https://r.jina.ai/" + url,
        headers={"User-Agent": "curl/8.23.0", "Accept": "text/plain"},
    )
    return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "ignore")


def _real_url(bing_url):
    m = re.search(r"[?&]u=a1([A-Za-z0-9_-]+)", bing_url)
    if not m:
        return bing_url
    b = m.group(1)
    b += "=" * (-len(b) % 4)
    try:
        return base64.urlsafe_b64decode(b).decode("utf-8", "ignore")
    except Exception:
        return bing_url


def _bing_search(query, n):
    txt = _jina("https://www.bing.com/search?q=" + urllib.parse.quote_plus(query), timeout=45)
    lines = txt.splitlines()
    out = []
    for i, ln in enumerate(lines):
        m = re.match(r"^\s*\d+\.\s+##\s+\[(.+?)\]\((https?://[^)]+)\)", ln)
        if not m:
            continue
        title = _strip_md(m.group(1))
        url = _real_url(m.group(2))
        snippet = ""
        for nxt in lines[i + 1:i + 4]:
            t = _strip_md(nxt)
            t = re.sub(r"^[A-Z][a-z]{2} \d{1,2}, \d{4}\s*·\s*", "", t)
            if len(t) > 20:
                snippet = t[:300]
                break
        out.append({"title": title, "url": url, "snippet": snippet})
        if len(out) >= n:
            break
    return out


def _fetch_page(url, max_chars=1800):
    try:
        txt = _jina(url, timeout=50)
        body = txt.split("Markdown Content:", 1)[-1]
        body = re.sub(r"\n{2,}", "\n", body)
        return _strip_md(body)[:max_chars]
    except Exception:
        return ""


def _jina_ddg(query, n):
    txt = _jina("https://html.duckduckgo.com/html/?q=" + urllib.parse.quote_plus(query))
    lines = txt.splitlines()
    out, cur = [], None
    for ln in lines:
        m = re.match(r"^#{2,3}\s+\[(.+?)\]\((https?://[^)]+)\)", ln)
        if m:
            if cur and cur["snippet"]:
                out.append(cur)
            href = m.group(2)
            q = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg")
            cur = {"title": m.group(1).strip(), "url": urllib.parse.unquote(q[0]) if q else href, "snippet": ""}
            if len(out) >= n:
                break
            continue
        if cur is not None:
            t = _strip_md(ln)
            if t and not t.startswith("http") and len(t) > 24 and "DuckDuckGo" not in t:
                cur["snippet"] = (cur["snippet"] + " " + t).strip()[:400]
    if cur and cur["snippet"] and len(out) < n:
        out.append(cur)
    return out[:n]


def _ddg_ia(query, n):
    url = "https://api.duckduckgo.com/?q=" + urllib.parse.quote_plus(query) + "&format=json&no_html=1&skip_disambig=1"
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    d = json.loads(urllib.request.urlopen(req, timeout=25).read())
    out = []
    if d.get("AbstractText"):
        out.append({"title": d.get("Heading") or query, "url": d.get("AbstractURL", ""), "snippet": d["AbstractText"][:400]})
    for t in d.get("RelatedTopics", []):
        if len(out) >= n:
            break
        if isinstance(t, dict) and t.get("Text"):
            out.append({"title": t["Text"].split(" - ")[0][:90], "url": t.get("FirstURL", ""), "snippet": t["Text"][:400]})
    return out[:n]


def _wikipedia(query, n):
    url = ("https://en.wikipedia.org/w/api.php?action=query&list=search&format=json&srlimit=%d&srsearch=" % n) + urllib.parse.quote_plus(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    d = json.loads(urllib.request.urlopen(req, timeout=25).read())
    out = []
    for hit in d.get("query", {}).get("search", []):
        out.append({
            "title": hit.get("title", ""),
            "url": "https://en.wikipedia.org/wiki/" + urllib.parse.quote(hit.get("title", "").replace(" ", "_")),
            "snippet": _strip_md(hit.get("snippet", ""))[:400],
        })
    return out[:n]


def ddg_search(query, n=5):
    results = []
    for fn in (_bing_search, _jina_ddg, _ddg_ia, _wikipedia):
        try:
            results = fn(query, n)
            if results:
                break
        except Exception:
            continue
    # dedupe by url
    seen, uniq = set(), []
    for r in results:
        u = r.get("url", "")
        if u and u not in seen:
            seen.add(u); uniq.append(r)
    results = uniq
    # deep read top pages with one retry
    for r in results[:2]:
        r["content"] = _fetch_page(r["url"], 1600)
        if not r["content"]:
            time.sleep(1.5)
            r["content"] = _fetch_page(r["url"], 1600)
        time.sleep(0.8)
    return results


def summarize(messages):
    transcript = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
    payload = {
        "messages": [
            {"role": "system", "content": SUMMARY_PROMPT},
            {"role": "user", "content": transcript[:24000]},
        ],
        "max_tokens": SUMMARY_MAX_TOKENS,
        "temperature": 0.2,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    r = llama_json("/v1/chat/completions", payload)
    return r["choices"][0]["message"]["content"].strip()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/health":
            return self._send(200, json.dumps({"llama": llama_health(), "ctx": CTX}))
        if self.path.startswith("/api/search"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query).get("q", [""])[0]
            try:
                return self._send(200, json.dumps({"results": ddg_search(q)}))
            except Exception as e:
                return self._send(200, json.dumps({"results": [], "error": str(e)}))
        path = "index.html" if self.path == "/" else self.path.lstrip("/")
        fp = os.path.normpath(os.path.join(STATIC, path))
        if not fp.startswith(STATIC) or not os.path.isfile(fp):
            return self._send(404, "not found", "text/plain")
        ctype = "text/html" if fp.endswith(".html") else "text/css" if fp.endswith(".css") else "application/javascript" if fp.endswith(".js") else "application/octet-stream"
        with open(fp, "rb") as f:
            return self._send(200, f.read(), ctype)

    def do_POST(self):
        ln = int(self.headers.get("Content-Length", "0"))
        try:
            body = json.loads(self.rfile.read(ln) or b"{}")
        except Exception:
            return self._send(400, json.dumps({"error": "bad json"}))
        if self.path != "/api/chat":
            return self._send(404, json.dumps({"error": "not found"}))
        try:
            self.chat(body)
        except BrokenPipeError:
            pass
        except Exception as e:
            try:
                self._sse({"type": "error", "error": str(e)})
            except Exception:
                pass

    # ---- SSE helpers ----
    def _headers_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()

    def _sse(self, obj):
        self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
        self.wfile.flush()

    def chat(self, body):
        messages = [{"role": m["role"], "content": m["content"]} for m in body.get("messages", [])]
        if not messages:
            return self._send(400, json.dumps({"error": "no messages"}))
        if not messages or messages[0].get("role") != "system":
            messages.insert(0, {"role": "system", "content": SYSTEM_PROMPT})
        think = bool(body.get("think", False))
        use_search = bool(body.get("search", False))

        self._headers_sse()

        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if use_search or re.match(r"(?i)^\s*search\b", last_user):
            q = re.sub(r"(?i)^\s*search[:\s]*", "", last_user).strip() or last_user
            try:
                results = ddg_search(q)
            except Exception as e:
                results = []
                self._sse({"type": "search", "count": 0, "error": str(e)})
            if results:
                self._sse({"type": "search", "count": len(results), "query": q})
                now = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
                parts = []
                for i, r in enumerate(results):
                    p = f"[{i+1}] {r['title']}\n{r['url']}\n{r['snippet']}"
                    if r.get("content"):
                        p += "\nExcerpt: " + r["content"][:1500]
                    parts.append(p)
                block = f"Web search results for '{q}' (retrieved {now}):\n\n" + "\n\n".join(parts)
                messages.insert(0, {"role": "system", "content": block})
                messages.insert(1, {"role": "system", "content": "Use the search results above when relevant. Cite sources as [n]."})

        # context accounting at 85%
        total_text = "\n".join(m["content"] for m in messages)
        used = count_tokens(total_text)
        self._sse({"type": "usage", "tokens": used, "ctx": CTX})
        if used > int(CTX * SUMMARY_RATIO) and len(messages) > 2:
            try:
                summary = summarize(messages[:-1])
                self._sse({"type": "summary", "text": summary})
                messages = [
                    {"role": "system", "content": "Lossless summary of the earlier conversation (all technical details preserved):\n\n" + summary},
                    messages[-1],
                ]
            except Exception as e:
                self._sse({"type": "summary_error", "error": str(e)})

        payload = {
            "messages": messages,
            "stream": True,
            "max_tokens": int(body.get("max_tokens", 2048)),
            "temperature": float(body.get("temperature", 0.4)),
            "top_p": 0.9,
            "repeat_penalty": 1.12,
            "chat_template_kwargs": {"enable_thinking": think},
        }
        req = urllib.request.Request(
            LLAMA + "/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=900) as r:
            for raw in r:
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    ev = json.loads(data)
                except Exception:
                    continue
                ch = (ev.get("choices") or [{}])[0]
                d = ch.get("delta") or {}
                rc = d.get("reasoning_content")
                if rc:
                    self._sse({"type": "reasoning", "text": rc})
                c = d.get("content")
                if c:
                    self._sse({"type": "content", "text": c})
        self._sse({"type": "done"})


def main():
    if not llama_health():
        print(f"[warn] llama-server not reachable at {LLAMA} (start it first)", file=sys.stderr)
    srv = ThreadingHTTPServer(("127.0.0.1", APP_PORT), Handler)
    print(f"UI on http://127.0.0.1:{APP_PORT}  (llama-server {LLAMA}, ctx {CTX})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
