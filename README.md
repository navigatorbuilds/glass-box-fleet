# Glass-Box Fleet

An enterprise agent fleet you can audit **without trusting anyone**: every agent action — including
every refusal — emits a post-quantum signed, hash-linked evidence record that a judge can verify
OFFLINE, on their own machine, with an open-source verifier that never phones home.

**Don't trust the demo — verify it.**

Live demo: <https://glass-box-fleet-795914174700.europe-west1.run.app>

Built during the All Things Agentic submission period (Aug 27–31, 2026) — see
[DISCLOSURE](#disclosure-pre-existing-work-incorporated) for exactly which parts are pre-existing.

## What it does

A procurement fleet runs a recognizable enterprise errand — research vendors, check the budget
mandate, issue a purchase intent, file the expense — and **seals each step the instant it happens**.
One step is deliberately over budget: the fleet refuses it, and *the refusal itself is sealed*. That
is the whole thesis in one frame — the evidence is strongest exactly where the agent said no.

A run produces seven records, in this order:

| # | `gbx_action` | what it is |
|---|---|---|
| 1–3 | `research_vendor` | three vendor quotes gathered |
| 4 | `check_budget_mandate` | scoped mandate read before spending |
| 5 | `purchase_intent.REFUSED` | over-cap intent **refused**, refusal sealed |
| 6 | `issue_purchase_intent` | the in-cap intent that was allowed |
| 7 | `file_expense_record` | the expense filed against it |

Every record is wire-format v7, `sig_algorithm = 1` (ML-DSA-65 / FIPS 204), `network_id =
glass-box-demo`. The purchase-intent vocabulary is deliberately **AP2-shaped** — it borrows the
Checkout-Mandate framing of Google's Agent Payments Protocol so the evidence slots into that world.
It is *not* an AP2 conformance claim, and no money moves: these are intents, not transactions.

## Architecture

ADK (Python) orchestrator + Gemini workers on Cloud Run → each tool action → `sealer` (Rust, built
on the published `elara-record` crate) → signed hash-linked record → Firestore mirror + per-run
downloadable `evidence.json` → verified with the published `elara-verify` (terminal or in-browser
WASM). Full diagram and trust boundaries: [`docs/architecture.md`](docs/architecture.md).

Verdicts are `CONSISTENT` — offline evidence-integrity — never "authorized" or "on-chain". This is a
signed evidence log, not a blockchain (see [Honest limits](#honest-limits)).

## How it maps to the Gemini Enterprise Agent Platform

GEAP is organized around four pillars — Build, Scale, Govern, Optimize. Glass-Box Fleet is an
**evidence layer on top of that platform, not a replacement for it**:

| GEAP pillar | What the platform gives you | What this project adds |
|---|---|---|
| **Build** | ADK, Gemini models, agent registry as the catalog of who exists | A live `/agents` registry where each agent's actions are bound to its sealed record trail |
| **Scale** | Cloud Run, async operations | Scale-to-zero deployment capped at 2 instances; async work bus (Pub/Sub when configured, in-process fallback so it stays green keyless) |
| **Govern** | Agent Identity — cryptographic ID per agent, every action logged against it inside Google's trust boundary | The same guarantee **outside** any trust boundary: scoped budget mandates enforced at act time, refusals receipted, and the whole log independently verifiable with no Google, no network, and no trust in us |
| **Optimize** | Unified trace viewing, agent observability | OpenTelemetry spans → Cloud Trace, with per-action evidence that survives the trace's retention window |

The honest one-line version: GEAP proves what happened *to Google*. This proves it *to anyone*.

## DISCLOSURE (pre-existing work incorporated)

Contest rules permit incorporating pre-existing code with disclosure. Exact versions, as pinned in
[`sealer/Cargo.toml`](sealer/Cargo.toml):

| Work | Version | License | Source | First published |
|---|---|---|---|---|
| `elara-record` — record format, ML-DSA-65 signing | `=0.3.0` (exact pin) | MIT OR Apache-2.0 | crates.io | 2026-07-18 |
| `dilithium-rs` — ML-DSA-65 backend | `=0.2.0` (exact pin) | MIT OR Apache-2.0 | crates.io | third-party |
| `elara-verify` — offline verifier CLI + WASM | `0.3.3` (judge installs it themselves) | MIT OR Apache-2.0 | crates.io | 2026-07-18 |
| Record wire-format spec, ACVP FIPS-204 vectors, verify fixtures | — | MIT OR Apache-2.0 | [navigatorbuilds/elara-mesh](https://github.com/navigatorbuilds/elara-mesh) | 2026-07 |

**Everything else in this repository was newly created during the submission period** — the agent
fleet, the orchestrator, the sealer service, the UI, the mandate layer, the Firestore store, the
deployment, this README. The dependency list above is the complete set of incorporated prior work,
and all of it was already public on crates.io before the hackathon began.

This repo is Apache-2.0 and carries **zero AGPL dependencies** — a judge can rebuild every byte of
the signing path from crates.io.

Entrant of record: Nenad Vasic, who also publishes the crates above. The project's ongoing
open-source maintainer is an AI agent operating under his receipted, revocable mandate — a live
instance of the governance mechanism this submission demonstrates.

## Spin-up

All commands below were run end-to-end on 2026-08-27 and produce the output shown.

### Run it locally — no cloud, no model key, no account

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cd sealer && cargo build --release && cd ..     # Rust 1.75+, crates.io deps only
PORT=8080 .venv/bin/python -m ui.server         # open http://localhost:8080
```

Click **Run fleet** (or `curl -X POST localhost:8080/run`) and watch the receipt chain grow. With no
credentials present the fleet runs in `direct` mode — real tool calls, real sealing, no model
inference — so the evidence path is fully exercisable by anyone, offline, for free.

The signing identity is generated on first run into a gitignored `sealer-identity.json`; no key
material ships in this repo.

### Verify the evidence — three independent ways

```bash
# 1) In the browser: open /verify.html — a WASM build of the published verifier.
#    Paste any record JSON (every row in the receipt chain has a "copy JSON" button).
#    Watch the network tab: nothing leaves your machine after page load.

# 2) The repo's own chain check:
./sealer/target/release/sealer --verify-chain evidence/records.jsonl
#    → OK: 7 record(s), every signature valid, every link intact

# 3) The published verifier, installed from crates.io — NOT from this repo:
cargo install elara-verify --features cli      # the --features cli flag is required
elara-verify one-record.json                   # any single record from evidence.json
```

> **The `--features cli` flag is not optional.** A bare `cargo install elara-verify` exits 0 and
> silently installs no binary, because the CLI is feature-gated. This trips people up; it is the one
> command to copy exactly.

Mandate *bundles* are verified on the `/verify.html` page, not by the CLI — the CLI verifies records,
anchors, seals and inclusion proofs, and has no bundle flag.

### Tamper test — the point of the whole thing

```bash
cp evidence/records.jsonl /tmp/t.jsonl
sed -i 's/19.5/91.5/' /tmp/t.jsonl                            # change one price
./sealer/target/release/sealer --verify-chain /tmp/t.jsonl
```

```
record 1 (01a0429b-337a-7dc2-98dc-852ab4442aed): stored record_hash does not match recomputed hash
```

Exit code 1, and it names the record that lied. (`evidence/` is gitignored, so run the fleet once
before this — the chain you tamper with should be one you watched get created.)

### Deploy your own

```bash
gcloud run deploy glass-box-fleet --source . --region europe-west1 \
  --allow-unauthenticated --max-instances=2

# optional persistent signer (otherwise a fresh demo identity per revision):
#   --set-secrets=/secrets/identity.json=YOUR_SECRET:latest
#   --set-env-vars=SEALER_IDENTITY=/secrets/identity.json
# optional durable chain across cold starts:
#   --set-env-vars=FIRESTORE=1,GOOGLE_CLOUD_PROJECT=your-project
```

Note that `--set-secrets` **replaces** the whole secret set on each call — pass every secret you want
in one command, or you will silently drop the others.

**A note on billing, because it is part of the design.** The model key and the infrastructure live in
two separate Google Cloud projects: the project holding the Gemini key has billing disabled outright,
so no amount of judge traffic can reach a payment method, while the infrastructure project carries
the billing account, a $5 budget alert, and a hard `--max-instances=2` cap. A demo that anyone can
hammer should not be able to bankrupt its author.

## Honest limits

We would rather you know these than discover them:

- The evidence log is a signed, hash-linked record chain in a published open format — **not a
  blockchain, not consensus-sealed**. Offline verification proves integrity and signer identity; it
  does not prove that any third party agreed.
- Records use ML-DSA-65 alone (FIPS 204). The optional SPHINCS+ leg is deliberately off: it costs
  ~130 ms and ~35 KB per signature, which is the wrong trade for a live demo.
- On Cloud Run the local `records.jsonl` is ephemeral; the Firestore mirror is what survives a cold
  start. Locally, the file *is* the truth.
- "Verified" means the evidence is internally consistent and correctly signed. It does not mean the
  agent's decision was *wise* — only that nobody can quietly change what it did.

## License

Apache-2.0 — see [LICENSE](LICENSE).
