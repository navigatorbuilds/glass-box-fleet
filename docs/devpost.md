# Glass-Box Fleet — Devpost submission text (draft; final pass Aug-30 with Nenad)

**Category: The Fortified Enterprise Fleet**

## Inspiration
Every agent demo asks you to believe it. Enterprises can't run on belief — they need evidence.
The rubric asks whether the video shows proof of action; we took that literally: here's proof
you don't have to take our word for.

## What it does
A procurement agent fleet (ADK orchestrator + research and intent workers on Gemini 3.5 via
Vertex AI) where **every tool action — including refusals — is sealed the instant it happens**
into a post-quantum-signed, hash-linked evidence record. The fleet is cataloged in an agent
registry; workers act under a budget mandate, and an over-budget purchase intent is **refused,
with the refusal itself sealed as evidence**. A judge can watch the receipt chain grow live,
download the run's `evidence.json`, flip one byte to watch verification fail, and verify the
untampered bundle **on their own machine, offline** — with `elara-verify`, an open-source
verifier published on crates.io since July 2026 that never phones home.

It catches bad input, refuses unauthorized actions, and makes tampering with its own record
detectable. **Don't trust the demo — verify it.**

## How we built it (stack mandate)
- **Gemini 3.5 Flash via Vertex AI** — all agent reasoning (Vertex logs double as cloud proof).
- **Google ADK (Python)** — orchestrator + two workers with tool-level delegation.
- **Cloud Run** — the entire backend (fleet + sealer + UI) in one self-contained service.
- **Firestore** — evidence record persistence.
- Sealer: a small Rust service built on the published `elara-record` crate — ML-DSA-65
  (FIPS 204) signatures, content hashing, per-run hash-linking.
- Registry, receipt-chain UI, OpenTelemetry spans → Cloud Trace for observability.

## Enterprise Fleet mapping
Agent registry (catalog + mandate scopes) · long-running asynchronous operations (queued fleet
runs, persistent evidence context) · compliance governance (budget mandates enforced and
evidenced; refusals receipted; the audit log is cryptographically tamper-evident and
independently verifiable — a stronger property than trust-me logging).

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
| elara-record | 0.3.0 | MIT OR Apache-2.0 | crates.io | 2026-07-18 |
| elara-verify | 0.3.3 | MIT OR Apache-2.0 | crates.io | 2026-07-18 |
| record wire-format spec, ACVP FIPS-204 vectors, verify fixtures | — | MIT OR Apache-2.0 | github.com/navigatorbuilds/elara-mesh | 2026-07 |

The submission creates software that enhances and builds upon those libraries: a new
application class (agentic enterprise audit trails) they did not previously power.
Entrant of record: Nenad Vasic — also the publisher of the crates above.

## Provenance (after you've seen it work)
The mandate contract demonstrated here is not a mock-up: the same mechanism governs this
repository's own AI contributor, which operates under the entrant's receipted, revocable,
scope-limited mandate with a public evidence trail.

## Try it
- Live demo: https://glass-box-fleet-795914174700.europe-west1.run.app
- Verify offline: `cargo install elara-verify` → `elara-verify evidence.json` (or the
  in-browser WASM verifier — no install, no network).
- Repo: https://github.com/navigatorbuilds/glass-box-fleet — spin-up instructions in README (tested copy-paste commands).

## What's next
The same evidence layer applied to real enterprise connectors — and the agent-payment
authorization space (AP2, x402, verifiable-intent), where "who authorized what, provably"
is becoming an insurance-eligibility question.
