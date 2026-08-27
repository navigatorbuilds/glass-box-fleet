# Glass-Box Fleet

An enterprise agent fleet you can audit **without trusting anyone**: every agent action — including
every refusal — emits a post-quantum signed, hash-linked evidence record that a judge can verify
OFFLINE, on their own machine, with an open-source verifier that never phones home.

**Don't trust the demo — verify it.**

**Runs on your machine in about two minutes, with no cloud account, no API key and no card**
([Spin-up](#spin-up)). There is deliberately no hosted instance to trust: the claim of this project
is that you do not have to take anyone's word for the evidence, and a live URL I control would be
exactly the wrong thing to ask you to take my word for. Deploy it yourself if you want one
([Deploy your own](#deploy-your-own)) — it fits inside Google Cloud's always-free tier.

Built during the All Things Agentic submission period (Aug 27–31, 2026) — see
[DISCLOSURE](#disclosure-pre-existing-work-incorporated) for exactly which parts are pre-existing.

## What it does

A procurement fleet runs a recognizable enterprise errand — research vendors, check the budget
mandate, issue a purchase intent, file the expense — and **seals each step the instant it happens**.

The order it is given does not fit: 400 seats at the best price is $7,800/month against a
$5,000/month mandate cap ([`mandates/demo.json`](mandates/demo.json), committed in the open — the cap
is policy, not a secret). Nothing scripts a refusal here; the fleet is told to order what was asked
for and let the mandate answer. It answers no, **the refusal is sealed as evidence**, and the fleet
replans down to the 256 seats that do fit. That is the whole thesis in one frame — the evidence is
strongest exactly where the agent said no.

Each run appends seven records to the chain, in this order:

| # | `gbx_action` | what it is |
|---|---|---|
| 1–3 | `research_vendor` | three vendor quotes gathered |
| 4 | `check_budget_mandate` | the $7,800/mo order checked against the scoped mandate |
| 5 | `purchase_intent.REFUSED` | that order attempted anyway and **refused**, refusal sealed |
| 6 | `issue_purchase_intent` | the replanned 256-seat order that fits, allowed |
| 7 | `file_expense_record` | the expense filed against it |

The log is append-only, so a second click adds seven more and the chain keeps growing across runs —
that is the point of hash-linking, not a bug. Every record is wire-format v7, `sig_algorithm = 1`
(ML-DSA-65 / FIPS 204), `network_id = glass-box-demo`. The purchase-intent vocabulary is deliberately **AP2-shaped** — it borrows the
Checkout-Mandate framing of Google's Agent Payments Protocol so the evidence slots into that world.
It is *not* an AP2 conformance claim, and no money moves: these are intents, not transactions.

## Architecture

An ADK (Python) orchestrator calls two Gemini workers as tools — research and intents — and each
tool action goes to `sealer` (Rust, built on the published `elara-record` crate) → signed
hash-linked record → per-run downloadable `evidence.json`, mirrored to Firestore when deployed →
verified with the published `elara-verify` (terminal or in-browser WASM). Runs locally as-is;
Cloud Run is optional. Full diagram and trust boundaries: [`docs/architecture.md`](docs/architecture.md).

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

### Turn the model on (optional, free)

The fleet runs its whole evidence arc with no model at all. To watch Gemini actually orchestrate it,
get an AI Studio key — free, no billing account, no card:

```bash
export GOOGLE_API_KEY=...        # aistudio.google.com/apikey
PORT=8080 .venv/bin/python -m ui.server
```

The run then reports `"mode":"adk"` instead of `"mode":"direct"`, and three agents on three models
divide the errand between them.

> **The free tier is 20 `generateContent` requests per day — per project, *per model*.** That last
> word is the useful part, and it is why this fleet runs `gemini-3.7-flash` (orchestrator),
> `gemini-3.6-flash` (intents) and `gemini-3.5-flash-lite` (research) rather than one model three
> times: three models are three separate daily buckets. Exhaustion arrives as a `429`, and any
> graceful fallback — including this one — will hide it from you unless you read the `mode` field.

Two more things measured the hard way, both of which fail *silently* into the fallback path:

- `thinking_budget=0` is **not** universally accepted. `gemini-3.7-flash` takes it;
  `gemini-3.6-flash` and `gemini-3.5-flash-lite` reject it with a bare `400 INVALID_ARGUMENT` that
  names no field. Hence `THINKING_OPTIONAL` in [`agents/fleet.py`](agents/fleet.py) — opt in per
  model, never assume.
- Workers are attached as `AgentTool`s, **not** as `sub_agents`. ADK's `transfer_to_agent` hands over
  control: the worker becomes the active agent, answers the user directly, and the orchestrator's
  task context does not travel with it. Live, that produced a research worker replying *"I require
  the specific list of vendor names"* and a chain that ended after the research beats — no budget
  check, no refusal, no expense.

### Deploy your own

Optional, and it fits in the always-free tier — Cloud Run's free grant is 2M requests/month and this
scales to zero. One caveat worth knowing before you start: the free tier still requires a billing
account linked to the project. With billing unlinked, these commands are refused outright — free
tier is not the same as no-billing-account. Everything above this section runs without any of it.

```bash
gcloud services enable run.googleapis.com firestore.googleapis.com
gcloud firestore databases create --location=europe-west1 --type=firestore-native
# grant the runtime service account roles/datastore.user

gcloud run deploy glass-box-fleet --source . --region europe-west1 \
  --allow-unauthenticated --max-instances=2 \
  --update-env-vars GOOGLE_CLOUD_PROJECT=your-project,FIRESTORE=1,MODEL_RUNS_PER_DAY=40 \
  --update-secrets GOOGLE_API_KEY=your-ai-studio-key-secret:latest

# optional persistent signer (otherwise a fresh demo identity per revision):
#   --update-secrets /secrets/identity.json=YOUR_SECRET:latest
#   --update-env-vars SEALER_IDENTITY=/secrets/identity.json
```

`--set-secrets` and `--set-env-vars` **replace** the whole set on each call — use the `--update-`
forms for additive changes or you will silently drop the others.

**A note on billing, because it is part of the design.** Inference here runs on an AI Studio key
whose project has **no billing account attached at all**, which makes overspend structurally
impossible rather than merely discouraged: the free tier does not degrade into paid usage, it stops
at `429`. That is a deliberate reversal — an earlier revision of this project ran inference on Vertex
AI under the Cloud Run service account, which is the cleaner enterprise story (no key to leak or
rotate) but requires a live billing account, and *a GCP budget is an alert, not a cap*. It emails
you; it never stops the spend. Since the guarantee this project sells is "you don't have to trust
anyone", the demo should not require trusting its author's budget discipline either. `MODEL_RUNS_PER_DAY`
caps model-backed runs on top of that; past the cap the fleet degrades to the keyless `direct` path,
so the evidence arc still completes and only the model narration stops.

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
