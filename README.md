# Redactly

### Instant document redaction for the enterprise.

Drop in a PDF and Redactly auto-detects and **truly redacts** every piece of sensitive data — names, emails, phone numbers, SSNs, account/card numbers, addresses, dates of birth — in seconds. It removes the underlying text, not just draws a black box over it.

Built for the **Cerebras × Google DeepMind Gemma 4 hackathon** (Enterprise Impact) — detection runs on **`gemma-4-31b` on Cerebras** (~1,500 tok/s).

## Why enterprise teams need it

- **True redaction.** The sensitive text is *removed* from the PDF, not hidden under a rectangle you can copy-paste back out.
- **Instant.** A document is scanned, classified and scrubbed in seconds, not sent to a manual review queue.
- **Runs in your environment.** Files never leave your server; nothing is retained.
- **Auditable.** Every redaction is categorized and counted.

## Run it

```bash
export CEREBRAS_API_KEY=csk-...     # your Cerebras key
pip install pymupdf
python3 server.py                   # → http://localhost:8130
```

## Stack

`gemma-4-31b` on Cerebras (PII detection) · PyMuPDF (true PDF redaction) · Python `http.server` · single-file front end.

> Handle only documents you are authorized to process.
