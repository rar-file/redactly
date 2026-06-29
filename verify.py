#!/usr/bin/env python3
"""End-to-end verify: POST sample.pdf to /api/redact, assert true redaction."""
import base64
import json
import os
import urllib.request

import fitz

HERE = os.path.dirname(os.path.abspath(__file__))
URL = "http://localhost:8130/api/redact"

with open(os.path.join(HERE, "sample.pdf"), "rb") as f:
    pdf_bytes = f.read()

body = json.dumps({"pdf_b64": base64.b64encode(pdf_bytes).decode("ascii")}).encode()
req = urllib.request.Request(URL, data=body,
                            headers={"Content-Type": "application/json"}, method="POST")
with urllib.request.urlopen(req, timeout=120) as resp:
    res = json.loads(resp.read().decode("utf-8"))

print("ok:", res.get("ok"))
print("total:", res.get("total"))
print("summary:", json.dumps(res.get("summary")))
print("before_png present:", bool(res.get("before_png")))
print("after_png present:", bool(res.get("after_png")))
print("redacted_pdf present:", bool(res.get("redacted_pdf")))

assert res.get("ok") is True, "ok != True"
assert res.get("total", 0) > 0, "total not > 0"
assert res.get("redacted_pdf"), "redacted_pdf missing"

# open redacted PDF, confirm SSN + email gone
dataurl = res["redacted_pdf"]
b64 = dataurl.split(",", 1)[1]
red_bytes = base64.b64decode(b64)
rdoc = fitz.open(stream=red_bytes, filetype="pdf")
red_text = ""
for p in rdoc:
    red_text += p.get_text()
rdoc.close()

ssn_gone = "123-45-6789" not in red_text
email_gone = "jonathan.whitfield@acme-global.com" not in red_text
print("SSN removed from redacted PDF:", ssn_gone)
print("Email removed from redacted PDF:", email_gone)

assert ssn_gone, "SSN still present - true redaction FAILED"
assert email_gone, "Email still present - true redaction FAILED"

print("\nRESULT: PASS")
