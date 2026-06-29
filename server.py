#!/usr/bin/env python3
"""Redactly backend - enterprise PDF redaction web app."""
import os
import re
import json
import base64
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fitz  # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8130"))
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
CEREBRAS_BASE = "https://api.cerebras.ai/v1"
MODEL = "gemma-4-31b"

CATEGORIES = [
    "Person name", "Email", "Phone", "SSN", "Account number",
    "Address", "Date of birth", "Customer/Employee ID",
]

PLACEHOLDER_HTML = b"""<!doctype html><html><head><meta charset="utf-8">
<title>Redactly</title></head><body style="font-family:sans-serif">
<h1>Redactly backend running</h1><p>index.html not found yet.</p></body></html>"""


# ---------------------------------------------------------------- detection
def call_gemma(full_text):
    """One call to Gemma on Cerebras. Returns list of {text, category} or []."""
    if not CEREBRAS_API_KEY:
        return []
    prompt = (
        "You are a PII/sensitive-data extraction engine. From the document text "
        "below, extract EVERY piece of personally identifying or sensitive "
        "business data. Return STRICT JSON only: a JSON array of objects with "
        'keys "text" and "category". "text" MUST be the exact substring as it '
        "appears in the document (verbatim, so it can be string-matched). "
        '"category" MUST be one of: ' + " | ".join(CATEGORIES) + ".\n"
        "Return ONLY the JSON array, no prose, no markdown.\n\n"
        "DOCUMENT TEXT:\n" + full_text
    )
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You output only strict JSON."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 4000,
    }).encode("utf-8")
    req = urllib.request.Request(
        CEREBRAS_BASE + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + CEREBRAS_API_KEY,
            "Accept": "application/json",
            "User-Agent": ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        content = data["choices"][0]["message"]["content"]
        return parse_items(content)
    except Exception as e:
        print("Gemma call failed:", repr(e))
        return []


def parse_items(content):
    """Robustly parse the model output into a list of {text, category}."""
    if not content:
        return []
    s = content.strip()
    # strip code fences
    s = re.sub(r"^```(?:json)?", "", s.strip())
    s = re.sub(r"```$", "", s.strip()).strip()
    # slice from first '[' to last ']'
    i, j = s.find("["), s.rfind("]")
    if i != -1 and j != -1 and j > i:
        s = s[i:j + 1]
    try:
        arr = json.loads(s)
    except Exception:
        return []
    out = []
    if isinstance(arr, list):
        for it in arr:
            if isinstance(it, dict):
                t = str(it.get("text", "")).strip()
                c = str(it.get("category", "")).strip() or "Other"
                if t:
                    out.append({"text": t, "category": c})
    return out


def regex_items(full_text):
    """Fallback regex detection so the demo is never empty."""
    out = []
    patterns = [
        ("Email", r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
        ("SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
        ("Phone", r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        ("Account number", r"\b\d{12,16}\b"),
    ]
    seen = set()
    for cat, pat in patterns:
        for m in re.finditer(pat, full_text):
            t = m.group(0).strip()
            key = (t, cat)
            if t and key not in seen:
                seen.add(key)
                out.append({"text": t, "category": cat})
    return out


def merge_items(a, b):
    seen = set()
    out = []
    for it in a + b:
        key = it["text"]
        if key not in seen:
            seen.add(key)
            out.append(it)
    return out


# ---------------------------------------------------------------- redaction
def render_png_dataurl(page):
    pix = page.get_pixmap(dpi=110)
    png = pix.tobytes("png")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def do_redact(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = ""
    for page in doc:
        full_text += page.get_text() + "\n"

    items = call_gemma(full_text)
    fallback = regex_items(full_text)
    if not items:
        items = fallback
    else:
        items = merge_items(items, fallback)

    # category counts and per-page redaction counts
    summary_counts = {}
    page_counts = [0] * doc.page_count

    for page in doc:
        page_hits = 0
        for it in items:
            text = it["text"]
            if not text:
                continue
            try:
                rects = page.search_for(text)
            except Exception:
                rects = []
            for rect in rects:
                page.add_redact_annot(rect, fill=(0, 0, 0))
                summary_counts[it["category"]] = summary_counts.get(it["category"], 0) + 1
                page_hits += 1
        if page_hits:
            try:
                page.apply_redactions()
            except Exception as e:
                print("apply_redactions failed:", repr(e))
        page_counts[page.number] = page_hits

    total = sum(summary_counts.values())
    summary = [{"category": c, "count": n} for c, n in
               sorted(summary_counts.items(), key=lambda kv: -kv[1])]

    # page with most redactions
    best = 0
    if page_counts:
        best = max(range(len(page_counts)), key=lambda i: page_counts[i])

    # BEFORE from fresh re-open of original bytes
    before_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    before_png = render_png_dataurl(before_doc[best])
    before_doc.close()

    # AFTER from redacted doc
    after_png = render_png_dataurl(doc[best])

    redacted_bytes = doc.tobytes()
    doc.close()
    redacted_dataurl = "data:application/pdf;base64," + base64.b64encode(redacted_bytes).decode("ascii")

    return {
        "ok": True,
        "total": total,
        "summary": summary,
        "before_png": before_png,
        "after_png": after_png,
        "redacted_pdf": redacted_dataurl,
    }


# ---------------------------------------------------------------- http
class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print("[http] " + (fmt % args))

    def _send(self, code, body, ctype):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, obj, code=200):
        self._send(code, json.dumps(obj), "application/json")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index.html"):
            path = os.path.join(HERE, "index.html")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            else:
                self._send(200, PLACEHOLDER_HTML, "text/html; charset=utf-8")
            return
        if self.path.startswith("/sample.pdf"):
            path = os.path.join(HERE, "sample.pdf")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._send(200, f.read(), "application/pdf")
            else:
                self._send_json({"ok": False, "error": "sample.pdf not found"}, 404)
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    def do_POST(self):
        if self.path.rstrip("/") != "/api/redact":
            self._send_json({"ok": False, "error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b""
            payload = json.loads(raw.decode("utf-8"))
            pdf_b64 = payload.get("pdf_b64", "")
            if "," in pdf_b64 and pdf_b64.strip().startswith("data:"):
                pdf_b64 = pdf_b64.split(",", 1)[1]
            pdf_bytes = base64.b64decode(pdf_b64)
            result = do_redact(pdf_bytes)
            self._send_json(result)
        except Exception as e:
            print("redact error:", repr(e))
            self._send_json({"ok": False, "error": str(e)})


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Redactly backend listening on 0.0.0.0:%d" % PORT)
    srv.serve_forever()


if __name__ == "__main__":
    main()
