#!/usr/bin/env python3
"""Redactly backend - enterprise PDF redaction web app."""
import os
import re
import json
import time
import base64
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import fitz  # PyMuPDF

HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get("PORT", "8130"))
CEREBRAS_API_KEY = os.environ.get("CEREBRAS_API_KEY", "")
CEREBRAS_BASE = "https://api.cerebras.ai/v1"
MODEL = "gemma-4-31b"

# Browser UA is REQUIRED: Cerebras' Cloudflare blocks the default urllib UA
# (error 1010). Pretend to be Chrome.
BROWSER_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

CATEGORIES = [
    "Person name", "Email", "Phone", "SSN", "Account number",
    "Address", "Date of birth", "Customer/Employee ID",
]

# Fast local detectors run on EVERY page so completeness never depends on the
# network. (account/card numbers 12-19 digits; obvious month-name & slash dates.)
REGEX_PATTERNS = [
    ("Email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("SSN", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("Phone", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("Account number", re.compile(r"\b\d{12,19}\b")),
    ("Date of birth", re.compile(
        r"\b(?:January|February|March|April|May|June|July|August|September|"
        r"October|November|December)\s+\d{1,2},?\s+\d{4}\b")),
    ("Date of birth", re.compile(r"\b\d{1,2}/\d{1,2}/\d{4}\b")),
]

PLACEHOLDER_HTML = b"""<!doctype html><html><head><meta charset="utf-8">
<title>Redactly</title></head><body style="font-family:sans-serif">
<h1>Redactly backend running</h1><p>index.html not found yet.</p></body></html>"""


# ---------------------------------------------------------------- detection
def parse_items(content):
    """Robustly parse model output into a list of {text, category}.

    Accepts a JSON array of {"text","category"} objects OR a JSON array of
    bare strings.
    """
    if not content:
        return []
    s = content.strip()
    s = re.sub(r"^```(?:json)?", "", s.strip())
    s = re.sub(r"```$", "", s.strip()).strip()
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
                c = str(it.get("category", "")).strip() or "PII (AI-detected)"
                if t:
                    out.append({"text": t, "category": c})
            elif isinstance(it, str):
                t = it.strip()
                if t:
                    out.append({"text": t, "category": "PII (AI-detected)"})
    return out


def call_gemma(full_text, max_tokens=4000):
    """One call to Gemma on Cerebras. Returns list of {text, category} or []."""
    items, _ = call_gemma_raw(full_text, max_tokens)
    return items


def call_gemma_raw(full_text, max_tokens=2000):
    """Call Gemma on Cerebras over a chunk of text.

    Returns (items, completion_tokens). Never raises is NOT guaranteed here -
    callers should wrap; the streaming worker does.
    """
    if not CEREBRAS_API_KEY or not full_text.strip():
        return [], 0
    prompt = (
        "You are a PII/sensitive-data extraction engine. From the document text "
        "below, extract EVERY piece of personally identifying or sensitive "
        "business data: person names, street addresses, employee/customer IDs, "
        "emails, phone numbers, SSNs, account numbers, dates of birth - anything "
        "PII. Return STRICT JSON only: a JSON array of objects with keys "
        '"text" and "category". "text" MUST be the exact verbatim substring as '
        "it appears in the document so it can be string-matched. "
        '"category" is a short label (e.g. Person name | Email | Phone | SSN | '
        "Account number | Address | Date of birth | Customer/Employee ID).\n"
        "Return ONLY the JSON array, no prose, no markdown.\n\n"
        "DOCUMENT TEXT:\n" + full_text
    )
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You output only strict JSON arrays."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
    }).encode("utf-8")
    req = urllib.request.Request(
        CEREBRAS_BASE + "/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + CEREBRAS_API_KEY,
            "Accept": "application/json",
            "User-Agent": BROWSER_UA,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    content = data["choices"][0]["message"]["content"]
    toks = 0
    try:
        toks = int(data.get("usage", {}).get("completion_tokens", 0))
    except Exception:
        toks = 0
    return parse_items(content), toks


def regex_items(full_text):
    """Whole-document regex detection (used by the non-streaming path)."""
    out = []
    seen = set()
    for cat, pat in REGEX_PATTERNS:
        for m in pat.finditer(full_text):
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
def render_png_dataurl(page, dpi=110):
    pix = page.get_pixmap(dpi=dpi)
    png = pix.tobytes("png")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def regex_redact_page(page, text, summary_counts):
    """Apply fast local-regex redactions to one page. Returns #rects redacted."""
    hits = 0
    seen = set()
    for cat, pat in REGEX_PATTERNS:
        for m in pat.finditer(text):
            t = m.group(0).strip()
            if not t or t in seen:
                continue
            seen.add(t)
            try:
                rects = page.search_for(t)
            except Exception:
                rects = []
            for r in rects:
                page.add_redact_annot(r, fill=(0, 0, 0))
                summary_counts[cat] = summary_counts.get(cat, 0) + 1
                hits += 1
    return hits


def redact_strings_page(page, items, summary_counts):
    """Redact AI-detected strings on one page. Returns #rects redacted."""
    hits = 0
    seen = set()
    for it in items:
        t = it["text"]
        if not t or t in seen:
            continue
        seen.add(t)
        try:
            rects = page.search_for(t)
        except Exception:
            rects = []
        for r in rects:
            page.add_redact_annot(r, fill=(0, 0, 0))
            summary_counts[it["category"]] = summary_counts.get(it["category"], 0) + 1
            hits += 1
    return hits


def _finish(doc, pdf_bytes, summary_counts, page_counts, t0):
    """Build the final summary / previews / redacted-PDF payload."""
    total = sum(summary_counts.values())
    summary = [{"category": c, "count": n} for c, n in
               sorted(summary_counts.items(), key=lambda kv: -kv[1])]

    n = doc.page_count
    best = 0
    if page_counts and n:
        best = max(range(n), key=lambda i: page_counts[i])

    # BEFORE from a fresh re-open of the original bytes.
    before_doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    before_png = render_png_dataurl(before_doc[best], dpi=100)
    before_doc.close()
    # AFTER from the redacted doc.
    after_png = render_png_dataurl(doc[best], dpi=100)

    redacted_bytes = doc.tobytes()
    redacted_dataurl = ("data:application/pdf;base64," +
                        base64.b64encode(redacted_bytes).decode("ascii"))
    return {
        "total": total,
        "summary": summary,
        "before_png": before_png,
        "after_png": after_png,
        "redacted_pdf": redacted_dataurl,
        "elapsed": round(time.time() - t0, 1),
    }


def do_redact(pdf_bytes):
    """Non-streaming single-shot redaction (kept for /api/redact + small docs)."""
    t0 = time.time()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    full_text = ""
    page_texts = []
    for page in doc:
        txt = page.get_text()
        page_texts.append(txt)
        full_text += txt + "\n"

    items = []
    try:
        items = call_gemma(full_text)
    except Exception as e:
        print("Gemma call failed:", repr(e))

    summary_counts = {}
    page_counts = [0] * doc.page_count
    for page in doc:
        h = regex_redact_page(page, page_texts[page.number], summary_counts)
        h += redact_strings_page(page, items, summary_counts)
        if h:
            try:
                page.apply_redactions()
            except Exception as e:
                print("apply_redactions failed:", repr(e))
        page_counts[page.number] = h

    payload = _finish(doc, pdf_bytes, summary_counts, page_counts, t0)
    doc.close()
    payload["ok"] = True
    return payload


def redact_stream(pdf_bytes, emit):
    """Streaming redaction. `emit(dict)` writes one NDJSON line + flushes.

    Strategy for ~200 pages in <20s:
      * Split into ~5-page chunks, fire Gemma calls for ALL chunks concurrently
        (ThreadPoolExecutor, network only - PyMuPDF is touched on this thread).
      * As each chunk's Gemma call returns, run fast regex redaction AND the
        AI-detected redactions for that chunk's pages here on the main thread,
        apply_redactions (TRUE redaction - text removed), then emit progress.
      * Regex runs for every page regardless of Gemma success, so completeness
        is guaranteed even if calls fail/timeout.
    """
    t0 = time.time()
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    n = doc.page_count
    emit({"type": "start", "pages": n})

    page_texts = [doc[i].get_text() for i in range(n)]

    summary_counts = {}
    page_counts = [0] * n
    total_tokens = 0
    items_count = 0
    pages_done = 0

    CHUNK = 5
    chunks = [list(range(i, min(i + CHUNK, n))) for i in range(0, n, CHUNK)]

    def worker(idxs):
        text = "\n\n".join("[Page %d]\n%s" % (j + 1, page_texts[j]) for j in idxs)
        try:
            items, toks = call_gemma_raw(text)
        except Exception as e:
            print("gemma chunk failed:", repr(e))
            items, toks = [], 0
        return idxs, items, toks

    with ThreadPoolExecutor(max_workers=14) as ex:
        futs = [ex.submit(worker, idxs) for idxs in chunks]
        for fut in as_completed(futs):
            try:
                idxs, items, toks = fut.result()
            except Exception:
                idxs, items, toks = [], [], 0
            total_tokens += toks
            for j in idxs:
                page = doc[j]
                h = regex_redact_page(page, page_texts[j], summary_counts)
                h += redact_strings_page(page, items, summary_counts)
                if h:
                    try:
                        page.apply_redactions()
                    except Exception as e:
                        print("apply_redactions failed:", repr(e))
                page_counts[j] = h
                items_count += h
            pages_done += len(idxs)
            elapsed = time.time() - t0
            tok_s = int(total_tokens / elapsed) if elapsed > 0 else 0
            emit({"type": "progress", "pages_done": pages_done,
                  "items": items_count, "tok_s": tok_s})

    payload = _finish(doc, pdf_bytes, summary_counts, page_counts, t0)
    doc.close()
    payload["type"] = "done"
    emit(payload)


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

    def _read_pdf_bytes(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b""
        payload = json.loads(raw.decode("utf-8"))
        pdf_b64 = payload.get("pdf_b64", "")
        if "," in pdf_b64 and pdf_b64.strip().startswith("data:"):
            pdf_b64 = pdf_b64.split(",", 1)[1]
        return base64.b64decode(pdf_b64)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_file(self, path, ctype, missing_json):
        if os.path.exists(path):
            with open(path, "rb") as f:
                self._send(200, f.read(), ctype)
        else:
            self._send_json(missing_json, 404)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index.html"):
            path = os.path.join(HERE, "index.html")
            if os.path.exists(path):
                with open(path, "rb") as f:
                    self._send(200, f.read(), "text/html; charset=utf-8")
            else:
                self._send(200, PLACEHOLDER_HTML, "text/html; charset=utf-8")
            return
        if self.path.startswith("/sample-large.pdf"):
            large = os.path.join(HERE, "sample_large.pdf")
            small = os.path.join(HERE, "sample.pdf")
            path = large if os.path.exists(large) else small
            self._serve_file(path, "application/pdf",
                             {"ok": False, "error": "no sample available"})
            return
        if self.path.startswith("/sample.pdf"):
            self._serve_file(os.path.join(HERE, "sample.pdf"), "application/pdf",
                             {"ok": False, "error": "sample.pdf not found"})
            return
        self._send_json({"ok": False, "error": "not found"}, 404)

    def _do_stream(self):
        # Stream NDJSON, flushing each line. HTTP/1.0 (default) -> close-delimited.
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        def emit(obj):
            try:
                self.wfile.write((json.dumps(obj) + "\n").encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

        try:
            pdf_bytes = self._read_pdf_bytes()
            redact_stream(pdf_bytes, emit)
        except Exception as e:
            print("redact_stream error:", repr(e))
            emit({"type": "error", "error": str(e)})

    def do_POST(self):
        route = self.path.rstrip("/")
        if route == "/api/redact_stream":
            self._do_stream()
            return
        if route == "/api/redact":
            try:
                pdf_bytes = self._read_pdf_bytes()
                self._send_json(do_redact(pdf_bytes))
            except Exception as e:
                print("redact error:", repr(e))
                self._send_json({"ok": False, "error": str(e)})
            return
        self._send_json({"ok": False, "error": "not found"}, 404)


def main():
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print("Redactly backend listening on 0.0.0.0:%d" % PORT)
    srv.serve_forever()


if __name__ == "__main__":
    main()
