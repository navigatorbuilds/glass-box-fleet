# Glass-Box Fleet

An enterprise agent fleet you can audit without trusting anyone: every agent action emits a
post-quantum signed, hash-linked evidence record a judge can verify OFFLINE — with an
open-source verifier that never phones home.

**Don't trust the demo — verify it.**

Built during the All Things Agentic submission period (Aug 27-31, 2026) — see DISCLOSURE below.

## Architecture (A1b — self-contained, no home infra, no consensus claims)
ADK (Python) orchestrator + 2 Gemini workers on Cloud Run → each tool action → `sealer`
(Rust, built on the published `elara-record` crate) → signed hash-linked record → Firestore →
per-run downloadable `evidence.json` mandate bundle → verify with published `elara-verify`
(terminal or in-browser WASM). Verdicts are `CONSISTENT` (offline evidence-integrity), never
"authorized/on-chain" — this is a signed evidence log, not a blockchain.

## DISCLOSURE (pre-existing code/work incorporated, per contest rules)
| Work | Version | License | Source | First published |
|---|---|---|---|---|
| elara-record (record format, ML-DSA-65 signing) | 0.3.0 | MIT OR Apache-2.0 | crates.io | 2026-07-18 |
| elara-verify (offline verifier CLI/WASM) | 0.3.3 | MIT OR Apache-2.0 | crates.io | 2026-07-18 |
| Record wire-format spec + ACVP FIPS-204 test vectors + verify example fixtures | — | MIT OR Apache-2.0 | github.com/navigatorbuilds/elara-mesh | 2026-07 |

Everything else — the agent fleet, orchestration, sealer service, UI, integration glue, this
repo — was newly created during the submission period, enhancing and building upon those
published libraries (new capability: agentic enterprise audit trails).

Entrant of record: Nenad Vasic (also the publisher of the crates above). The project's ongoing
open-source maintainer is an AI agent operating under his receipted, revocable mandate — see
PROVENANCE in docs/ — a live instance of the governance mechanism this submission demonstrates.

## Spin-up (tested commands)

### Run locally (no cloud, no model key needed — "direct" demo mode)
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd sealer && cargo build --release && cd ..          # Rust 1.75+; crates.io deps only
PORT=8080 .venv/bin/python -m ui.server              # open http://localhost:8080
# click "Run fleet" (or: curl -X POST localhost:8080/run) — watch the receipt chain grow
```

### Verify the evidence — three independent ways
```bash
# 1) In the browser: /verify.html — WASM build of the open-source verifier; no network after load.
# 2) The repo's own chain check:
./sealer/target/release/sealer --verify-chain evidence/records.jsonl
# 3) The published verifier (installs from crates.io — not this repo):
cargo install elara-verify
elara-verify one-record.json        # any single record extracted from evidence.json
```

### Tamper test (the point of the whole thing)
```bash
cp evidence/records.jsonl /tmp/t.jsonl
sed -i 's/21.0/91.0/' /tmp/t.jsonl                   # flip one value
./sealer/target/release/sealer --verify-chain /tmp/t.jsonl   # names the record, exits 1
```

### Deploy your own (Google Cloud)
```bash
gcloud run deploy glass-box-fleet --source . --region europe-west1 --allow-unauthenticated
# optional persistent signer: put an identity JSON in Secret Manager and mount it:
#   --update-secrets=/secrets/identity.json=YOUR_SECRET:latest \
#   --update-env-vars=SEALER_IDENTITY=/secrets/identity.json
# with Vertex AI credentials the /run endpoint uses the live Gemini fleet; without, direct mode.
```
