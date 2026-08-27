# Video plan (≤3:30 target, 4:00 hard truncation) — per panel verdict fd7a876a

RULES BINDING: "unedited, live execution" (Proof of Action rubric line) — the fleet-run and
tamper segments are SINGLE TAKES, terminal/UI visible throughout. Captions only (no voice).
Nenad approves final cut (his Devpost account). Disclosure caption card at the close.

## Shot list
1. **0:00-0:10 COLD OPEN** — 3s pre-roll of the tamper moment (red row flash), then title card:
   "Every agent demo asks you to believe it. This one doesn't." (If Veo bonus lands: Veo-generated
   3s title backdrop, +0.2.)
2. **0:10-1:35 THE FLEET (single take)** — split screen: left = /run trigger + agent output;
   right = receipt chain growing row by row. Beats inside the take: registry view flash
   (/agents), the budget-mandate check sealing, the over-budget intent REFUSED (red row =
   "the refusal is itself evidence" caption), expense filed.
3. **1:35-1:55 THE MODEL IS ACTUALLY DRIVING** — one decisive screen, replacing the old Cloud Run
   console shot (there is no hosted instance any more — see README, that is deliberate). Show the
   `/run` response with `"mode":"adk"` and the event count, next to `agents/fleet.py` with the
   three model names visible: `gemini-3.7-flash` orchestrating, `gemini-3.6-flash` on intents,
   `gemini-3.5-flash-lite` on research. Caption: "three agents, three models — and the free tier
   meters per model, so this runs on a project with no billing account at all." Stronger than a
   console page: it answers "is a script faking this?", which is what a judge is really asking.
   No slow pans.
4. **1:55-2:25 TAMPER (single take)** — download evidence.json → flip one byte in an editor,
   on camera → verifier names the record and fails (exit 1 in terminal) → undo → green.
5. **2:25-3:05 THE MONEY SHOT** — the judge's experience: open /verify.html → load the bundle →
   all rows green → **toggle wifi OFF on camera** → verify again (still works — zero network) →
   then same verdict from `elara-verify` in a terminal ("that verifier isn't part of this demo —
   it's been public on crates.io since July; run it yourself in six months, same answer").
6. **3:05-3:25 CLOSE** — copy-paste verify command on screen + caption:
   "Don't trust the demo — verify it." + one governance line: "the mandate contract you just
   watched governs this repo's own AI contributor — public trail in the README." + disclosure
   caption card (crates named, MIT/Apache, crates.io July 2026).

## Capture checklist
- [ ] Fresh /run immediately before recording (chain starts clean, <10 rows — legible).
- [ ] Terminal font ≥16pt; browser zoom 125%; single 1080p display region.
- [ ] The tamper take: pre-choose the byte (a visible price digit), rehearse undo.
- [ ] Wifi-toggle shot: verify page ALREADY LOADED before toggling (wasm cached — honest:
      caption says "no network after load").
- [ ] Lyria background bed (+0.2) if bonus lane lands; else silent + captions.
- [ ] End-card: repo URL + live URL + "verify offline" command.
