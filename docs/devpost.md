# Glass-Box Fleet — Devpost submission text (draft; final pass Aug-30 with Nenad)

**Category: The Fortified Enterprise Fleet**

## Inspiration
Every agent demo asks you to believe it. Enterprises can't run on belief — they need evidence.
The rubric asks whether the video shows proof of action; we took that literally: here's proof
you don't have to take our word for.

## What it does
A procurement agent fleet (an ADK orchestrator calling research and intent workers as tools, each
on its own Gemini model) where **every tool action — including refusals — is sealed the instant it happens**
into a post-quantum-signed, hash-linked evidence record. The fleet is cataloged in an agent
registry; workers act under a budget mandate, and an over-budget purchase intent is **refused,
with the refusal itself sealed as evidence**. A judge can watch the receipt chain grow live,
download the run's `evidence.json`, flip one byte to watch verification fail, and verify the
untampered bundle **on their own machine, offline** — with `elara-verify`, an open-source
verifier published on crates.io since July 2026 that never phones home.

It catches bad input, refuses unauthorized actions, and makes tampering with its own record
detectable. **Don't trust the demo — verify it.**

## How we built it (stack mandate)
- **Gemini, three models, one per agent** — `gemini-3.7-flash` orchestrates, `gemini-3.6-flash`
  handles intents, `gemini-3.5-flash-lite` does research lookups. Not decoration: the free tier
  meters requests per project *per model*, so three agents on three models draw three separate
  daily buckets, and the whole fleet runs on an AI Studio key whose project has **no billing
  account attached** — overspend is structurally impossible, not merely budgeted against.
- **Google ADK (Python)** — an orchestrator that keeps control, calling both workers as `AgentTool`s
  rather than transferring to them as `sub_agents`, with HTTP-layer retry so a transient `503`
  never replays an errand that has already sealed records.
- **Cloud Run** — the entire backend (fleet + sealer + UI) in one self-contained service, scale-to-zero,
  `--max-instances=2`, with a daily model-run cap that degrades to a fully keyless path instead of failing.
- **Firestore** — evidence record persistence across cold starts and revisions.
- Sealer: a small Rust service built on the published `elara-record` crate — ML-DSA-65
  (FIPS 204) signatures, content hashing, per-run hash-linking.
- Registry, receipt-chain UI, OpenTelemetry spans → Cloud Trace for observability.

## Enterprise Fleet mapping — the four GEAP pillars
Gemini Enterprise Agent Platform is organized around Build, Scale, Govern and Optimize. This is an
**evidence layer on top of that platform, not a replacement for any of it**:

| GEAP pillar | What the platform gives you | What this adds |
|---|---|---|
| **Build** | ADK, Gemini, an agent registry cataloging who exists | A live `/agents` registry where each agent's actions are bound to its own sealed record trail |
| **Scale** | Cloud Run, long-running async operations | Scale-to-zero, capped instances, async work bus (Pub/Sub when configured, in-process fallback so it stays green keyless) |
| **Govern** | Agent Identity — a cryptographic ID per agent, every action logged against it inside Google's trust boundary | The same guarantee **outside** any trust boundary: budget mandates enforced at act time, refusals receipted, the whole log verifiable with no Google, no network, and no trust in us |
| **Optimize** | Unified trace viewing and agent observability | OpenTelemetry spans → Cloud Trace, plus evidence that outlives the trace retention window |

The one-line version: GEAP proves what happened *to Google*. This proves it *to anyone*.

## Honest limits (we'd rather you know)
The evidence log is a signed, hash-linked record chain in a published open format — **not a
blockchain and not consensus-sealed**. Offline verification proves integrity and signer
("CONSISTENT"/"VERIFIED"), never "authorized on some chain", and a bundle cannot reveal a
revocation its author withheld. Vendor data in the demo is canned; purchase intents move no
money. Fresh start is the point: nothing in verification depends on our servers existing.

## Disclosure (pre-existing code/work incorporated)
Built during the submission period: the entire fleet, orchestration, sealer service, UI and
integration. Incorporates the entrant's pre-existing open-source libraries, as permitted with
disclosure — enumerated:

| Work | Version | License | Source | First published |
|---|---|---|---|---|
| elara-record (record format, ML-DSA-65 signing) | `=0.3.0` exact pin | MIT OR Apache-2.0 | crates.io | 2026-07-18 |
| dilithium-rs (ML-DSA-65 backend) | `=0.2.0` exact pin | MIT OR Apache-2.0 | crates.io | third-party |
| elara-verify (offline verifier CLI + WASM) | 0.3.3, installed by the judge | MIT OR Apache-2.0 | crates.io | 2026-07-18 |
| record wire-format spec, ACVP FIPS-204 vectors, verify fixtures | — | MIT OR Apache-2.0 | github.com/navigatorbuilds/elara-mesh | 2026-07 |

That table is the complete set of incorporated prior work, and all of it was public on crates.io
before the hackathon began. The submission creates software that enhances and builds upon those
libraries: a new application class (agentic enterprise audit trails) they did not previously power.
The repo is Apache-2.0 with **zero AGPL dependencies** — the entire signing path is rebuildable
from crates.io.
Entrant of record: Nenad Vasic — also the publisher of the crates above.

## Provenance (after you've seen it work)
The mandate contract demonstrated here is not a mock-up: the same mechanism governs this
repository's own AI contributor, which operates under the entrant's receipted, revocable,
scope-limited mandate with a public evidence trail.

## Try it
- **Run it yourself in about two minutes** — no cloud account, no API key, no card:
  `pip install -r requirements.txt`, `cargo build --release` in `sealer/`, then
  `python -m ui.server`. There is deliberately no hosted instance: the claim here is that you don't
  have to take anyone's word for the evidence, and a live URL we control is exactly the wrong thing
  to ask you to take our word for. The video shows the same run end to end.
- Verify offline: `cargo install elara-verify --features cli` → `elara-verify one-record.json`
  (the `--features cli` flag is required — a bare install exits 0 and installs nothing). Or use
  the in-browser WASM verifier: no install, no network, paste any record from the chain.
- Repo: https://github.com/navigatorbuilds/glass-box-fleet — spin-up instructions in README (tested copy-paste commands).

## What's next
The same evidence layer applied to real enterprise connectors — and the agent-payment
authorization space (AP2, x402, verifiable-intent), where "who authorized what, provably"
is becoming an insurance-eligibility question.
