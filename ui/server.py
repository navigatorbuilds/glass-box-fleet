"""Glass-Box Fleet UI — receipt chain, agent registry, evidence bundle, run trigger.

Server-rendered HTML with a 2-second vanilla-JS poll (no build step). Reads the same
append-only evidence log the sealer writes (`evidence/records.jsonl`); every row's
chain badge is a display-level continuity check — the cryptographic truth lives in
`sealer --verify-chain` / the published offline verifier, and the page says so.

Run locally:  python -m ui.server           (binds 0.0.0.0:$PORT, default 8080)
Routes:       GET /            receipt-chain page (auto-refreshing)
              GET /agents      fleet registry (static JSON mirror of agents/fleet.py)
              GET /evidence.json   downloadable bundle of the run's records
              POST /run        one fleet run (ADK if credentials exist, else the
                               keyless direct-tool demo path — marked "direct")
"""
from __future__ import annotations

import asyncio
import html
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI  # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

EVIDENCE_DIR = Path(os.environ.get("GLASSBOX_EVIDENCE_DIR", "evidence"))
RUN_LOG = EVIDENCE_DIR / "records.jsonl"
GENESIS_PREV = "0" * 64

app = FastAPI(title="Glass-Box Fleet")

UI_DIR = Path(__file__).resolve().parent
app.mount("/wasm", StaticFiles(directory=UI_DIR / "wasm"), name="wasm")


@app.get("/verify.html")
def verify_page() -> FileResponse:
    """In-browser offline verifier (elara-verify compiled to WASM; no network after load)."""
    return FileResponse(UI_DIR / "verify.html")

# Last run's mode ("adk" | "direct" | error text) — display state only.
_last_run: dict = {"mode": None, "detail": "", "at": None}
_run_lock = threading.Lock()

# Static registry mirror of agents/fleet.py (kept in sync by hand — the page
# must stay serveable with no model credentials and no ADK import at request
# time). Mandate scopes describe the demo contract, not real spending power.
FLEET_REGISTRY = [
    {
        "name": "procurement_orchestrator",
        "model": "gemini-3.5-flash",
        "mandate_scope": "delegate-only: routes work to workers, holds no tools",
        "version": "0.1.0",
        "status": "ready",
    },
    {
        "name": "research_worker",
        "model": "gemini-3.5-flash",
        "mandate_scope": "read-only vendor research over canned demo data",
        "version": "0.1.0",
        "status": "ready",
    },
    {
        "name": "intent_worker",
        "model": "gemini-3.5-flash",
        "mandate_scope": "purchase INTENTS only, budget-capped at 500 USD/month; refusals are sealed too",
        "version": "0.1.0",
        "status": "ready",
    },
]


def load_envelopes() -> list[dict]:
    """Sealed envelopes in chain order — Firestore mirror when FIRESTORE=1 and
    reachable (Cloud Run: survives revisions), else the local jsonl. Parse
    failures become {"UNPARSEABLE_LINE": raw} sentinels."""
    from glassbox import store

    remote = store.read_all()
    if remote is not None:
        return remote
    out: list[dict] = []
    if RUN_LOG.exists():
        for raw in RUN_LOG.read_text().splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                out.append(json.loads(raw))
            except json.JSONDecodeError:
                out.append({"UNPARSEABLE_LINE": raw})
    return out


def read_rows() -> list[dict]:
    """Parse the evidence log into display rows with a continuity badge.

    Badge semantics (display-level): OK = this record's signed prev pointer
    equals the previous sealed record's hash; BROKEN = it does not (or the
    line is unparseable); STUB = an unsigned placeholder row from the
    pre-sealer wiring — loud, red, never presentable.
    """
    rows: list[dict] = []
    expected_prev = GENESIS_PREV
    for i, line in enumerate(load_envelopes()):
        if "UNPARSEABLE_LINE" in line:
            rows.append({"index": i, "badge": "BROKEN", "agent": "?", "action": "unparseable line",
                         "ts": "", "record_id": "", "mode": ""})
            continue
        if line.get("UNSIGNED_STUB"):
            ev = line.get("event", {})
            rows.append({"index": i, "badge": "STUB", "agent": ev.get("agent", "?"),
                         "action": ev.get("action", "?"), "ts": str(ev.get("ts", "")),
                         "record_id": "(unsigned stub)", "mode": ""})
            continue
        rec = line.get("record", {})
        meta = rec.get("metadata", {})
        prev = meta.get("gbx_prev_record_hash", "")
        ok = prev == expected_prev
        if ok:
            expected_prev = line.get("record_hash", "")
        rows.append({
            "index": i,
            "badge": "OK" if ok else "BROKEN",
            "agent": meta.get("gbx_agent", "?"),
            "action": meta.get("gbx_action", "?"),
            "ts": str(meta.get("gbx_ts", "")),
            "record_id": rec.get("id", "?"),
            "mode": meta.get("gbx_params", {}).get("run_mode", "") if isinstance(meta.get("gbx_params"), dict) else "",
        })
    return rows


def rows_fragment() -> str:
    rows = read_rows()
    if not rows:
        return '<tr><td colspan="7" class="empty">no records yet — POST /run (or the Run button) to grow the chain</td></tr>'
    out = []
    for r in rows:
        badge_class = {"OK": "ok", "BROKEN": "broken", "STUB": "stub"}[r["badge"]]
        # Mandate refusals get the red-shield mark on the action cell — the
        # refusal is a first-class sealed record, verifiable like any other.
        refused = r["action"].endswith(".REFUSED")
        action_cell = (
            f'<span class="badge refused">🛡 REFUSED</span> {html.escape(r["action"])}'
            if refused
            else html.escape(r["action"])
        )
        mode_mark = f' <em>({html.escape(r["mode"])})</em>' if r["mode"] else ""
        out.append(
            "<tr>"
            f'<td>{r["index"]}</td>'
            f'<td>{html.escape(r["agent"])}</td>'
            f"<td>{action_cell}{mode_mark}</td>"
            f'<td>{html.escape(r["ts"])}</td>'
            f'<td class="mono">{html.escape(r["record_id"])}</td>'
            f'<td><span class="badge {badge_class}">{r["badge"]}</span></td>'
            f'<td><button class="copy" onclick="copyRecord({r["index"]})">copy JSON</button></td>'
            "</tr>"
        )
    return "".join(out)


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Glass-Box Fleet — receipt chain</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111; }}
  h1 {{ font-size: 1.3rem; }} .sub {{ color: #555; max-width: 60rem; }}
  table {{ border-collapse: collapse; margin-top: 1rem; width: 100%; }}
  th, td {{ text-align: left; padding: .35rem .6rem; border-bottom: 1px solid #ddd; font-size: .9rem; }}
  .mono {{ font-family: ui-monospace, monospace; font-size: .8rem; }}
  .badge {{ padding: .1rem .5rem; border-radius: .6rem; font-weight: 600; font-size: .8rem; }}
  .ok {{ background: #d7f5dd; color: #135b22; }}
  .broken {{ background: #ffd6d6; color: #8f0d0d; }}
  .stub {{ background: #ff2d2d; color: #fff; }}
  .refused {{ background: #8f0d0d; color: #fff; }}
  .copy {{ font-size: .75rem; padding: .15rem .5rem; }}
  .empty {{ color: #777; font-style: italic; }}
  button {{ padding: .4rem 1rem; font-size: 1rem; cursor: pointer; }}
  #runinfo {{ margin-left: 1rem; color: #555; }}
</style></head>
<body>
<h1>Glass-Box Fleet — receipt chain</h1>
<p class="sub">Every agent action below is a signed, hash-linked evidence record (published
<code>elara-record</code> format, ML-DSA-65). The badge is a display-level continuity check —
the cryptographic verdict comes from the offline verifier
(<code>sealer --verify-chain evidence/records.jsonl</code>), which anyone can run without
this server. This is a signed evidence log, not a blockchain.</p>
<p><button id="runbtn" onclick="kick()">Run fleet once</button><span id="runinfo"></span></p>
<table>
<thead><tr><th>#</th><th>agent</th><th>action</th><th>ts</th><th>record id</th><th>chain</th><th></th></tr></thead>
<tbody id="rows">{rows}</tbody>
</table>
<script>
  async function poll() {{
    try {{
      const r = await fetch('/?fragment=1');
      document.getElementById('rows').innerHTML = await r.text();
    }} catch (e) {{ /* keep last view on transient errors */ }}
  }}
  setInterval(poll, 2000);
  async function copyRecord(i) {{
    const r = await fetch('/evidence.json');
    const j = await r.json();
    await navigator.clipboard.writeText(JSON.stringify(j.records[i], null, 2));
  }}
  async function kick() {{
    const btn = document.getElementById('runbtn');
    const info = document.getElementById('runinfo');
    btn.disabled = true; info.textContent = 'running…';
    try {{
      const r = await fetch('/run', {{method: 'POST'}});
      const j = await r.json();
      info.textContent = 'last run: ' + j.mode + (j.detail ? ' — ' + j.detail : '');
    }} catch (e) {{ info.textContent = 'run failed: ' + e; }}
    btn.disabled = false;
  }}
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
def chain_page(fragment: int = 0) -> Response:
    if fragment:
        return HTMLResponse(rows_fragment())
    return HTMLResponse(PAGE.format(rows=rows_fragment()))


@app.get("/agents")
def agents() -> JSONResponse:
    return JSONResponse({"fleet": FLEET_REGISTRY, "last_run": _last_run})


@app.get("/evidence.json")
def evidence_bundle() -> Response:
    records = load_envelopes()
    body = json.dumps(
        {
            "bundle": "glass-box-fleet evidence log",
            "note": "signed, hash-linked records in the published elara-record format; "
                    "verify offline with `sealer --verify-chain` — not a blockchain",
            "count": len(records),
            "records": records,
        },
        indent=2,
    )
    return Response(
        content=body,
        media_type="application/json",
        headers={"Content-Disposition": 'attachment; filename="evidence.json"'},
    )


def _using_vertex() -> bool:
    """Vertex AI via the runtime service account — no API key anywhere.

    This is the deployed path. The AI Studio key path it replaced is capped at
    20 requests/day/model on the free tier (verified against a live 429 on
    2026-08-27), which two judge clicks exhaust."""
    return os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").upper() in {"1", "TRUE", "YES"} \
        and bool(os.environ.get("GOOGLE_CLOUD_PROJECT"))


def _have_model_credentials() -> bool:
    if _using_vertex():
        return True
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    adc = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return adc.exists()


# Spend guard. Moving the model path onto Vertex put it on a project that has a
# real billing account, so "a judge cannot reach a payment method" is no longer
# structurally true and must be enforced here instead of asserted in the README.
# Beyond the cap the run still completes — it degrades to the keyless `direct`
# path, so the evidence story never breaks, only the model narration stops.
MODEL_RUNS_PER_DAY = int(os.environ.get("MODEL_RUNS_PER_DAY", "200"))
_model_budget = {"day": "", "used": 0}


def _model_budget_available() -> bool:
    """Best-effort daily cap on model-backed runs. Per-instance, and the service
    is pinned to --max-instances=2, so the true ceiling is 2x the configured
    number — deliberately stated rather than hidden."""
    today = time.strftime("%Y-%m-%d", time.gmtime())
    if _model_budget["day"] != today:
        _model_budget.update({"day": today, "used": 0})
    return _model_budget["used"] < MODEL_RUNS_PER_DAY


def _run_direct(why: str = "no model credentials") -> dict:
    """Keyless demo path: exercise the sealed research tool directly so the
    chain grows without any LLM. Rows are marked "direct" via params.

    `why` states the actual reason this path ran — the fallback from a failed
    ADK run passes its own, so the detail line never claims "no credentials"
    on a box that has them."""
    from agents import fleet  # deferred: pulls google-adk, never at page load

    fleet.RUN_MODE = "direct"
    try:
        best_vendor, best_price = "", float("inf")
        for vendor in list(fleet.MOCK_VENDORS):
            result = fleet.research_vendor(vendor)
            price = result.get("offer", {}).get("unit_price_usd")
            if isinstance(price, (int, float)) and price < best_price:
                best_vendor, best_price = vendor, float(price)
        # The climax beat. Same arithmetic the model does on the ADK path, so
        # both paths tell one story: the full order is over the mandate cap and
        # is REFUSED (sealed), then the largest order that fits goes through
        # (sealed). Derived from the mandate file, never a magic number — a
        # hardcoded over-cap amount would still "work" if someone raised the cap
        # and stopped being a refusal, silently.
        from glassbox import mandate

        cap = float(mandate.get_mandate().get("cap_usd", 0))
        requested = round(best_price * SEATS_REQUESTED, 2)
        affordable_seats = int(cap // best_price)
        fits = round(best_price * affordable_seats, 2)
        fleet.check_budget_mandate(requested)
        refused = fleet.issue_purchase_intent(best_vendor, requested)
        issued = fleet.issue_purchase_intent(best_vendor, fits)
        fleet.file_expense_record(issued.get("intent_id", "?"), best_vendor, fits)
        detail = (
            f"research x3 → {SEATS_REQUESTED} seats at ${requested:,.2f}/mo "
            f"{refused.get('status')} ({refused.get('reason')}, cap ${cap:,.0f}) → "
            f"replanned to {affordable_seats} seats at ${fits:,.2f}/mo "
            f"{issued.get('status')} → expense filed "
            f"({why} — direct tool calls, every step sealed)"
        )
    finally:
        fleet.RUN_MODE = ""
    return {"mode": "direct", "detail": detail}


# 400 seats at the cheapest vendor ($19.5/unit) is $7,800/month against a
# $5,000 mandate cap, so the fleet's honest first attempt is over-cap and the
# refusal is EMERGENT rather than scripted — the model then has to replan down
# to a seat count that fits. The old prompt ("within the monthly budget") let
# the model quietly stay in-cap and the refusal record never appeared, which
# removed the one beat the whole submission is about.
SEATS_REQUESTED = 400
ADK_PROMPT = (
    f"Procure object storage for the whole fleet: {SEATS_REQUESTED} seats, billed monthly. "
    "Work under the standing procurement mandate."
)
ADK_USER_ID = "glassbox-demo"


def _await_blocking(coro):
    """Drive a coroutine to completion from synchronous code.

    /run is a sync FastAPI endpoint, so it executes on a threadpool worker with
    no running event loop and asyncio.run() is the correct driver there. The
    thread branch keeps this honest if it is ever called from inside a loop
    (asyncio.run() raises rather than nesting)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


async def _run_adk_async() -> dict:
    """One LLM-orchestrated fleet run under the ADK Runner.

    The whole Runner API is async — run_async() is an async generator and even
    run_debug() is a coroutine — so the run has to be driven from an event loop.
    Calling it from sync code just yields an un-awaited coroutine object, which
    is what produced the "object of type 'coroutine' has no len()" fallback.
    run_async() is ADK's documented production entrypoint (run_debug is marked
    debugging-only), so the session is created explicitly and the event stream
    consumed here."""
    from agents import fleet  # deferred: pulls google-adk, never at page load
    from google.adk.runners import InMemoryRunner
    from google.genai import types

    runner = InMemoryRunner(agent=fleet.root_agent)
    fleet.RUN_MODE = "adk"  # the dispatch path is sealed INSIDE params, like direct/async
    try:
        session = await runner.session_service.create_session(
            app_name=runner.app_name, user_id=ADK_USER_ID
        )
        message = types.Content(role="user", parts=[types.Part(text=ADK_PROMPT)])
        events, final_text = 0, ""
        async for event in runner.run_async(
            user_id=ADK_USER_ID, session_id=session.id, new_message=message
        ):
            events += 1
            if event.is_final_response() and event.content and event.content.parts:
                final_text = " ".join(
                    (part.text or "").strip() for part in event.content.parts
                ).strip()
    finally:
        fleet.RUN_MODE = ""
        await runner.close()
    summary = final_text.replace("\n", " ")
    if len(summary) > 400:
        summary = summary[:400] + "…"
    detail = f"{events} ADK events (model-orchestrated, every tool call sealed)"
    return {"mode": "adk", "detail": f"{detail} — {summary}" if summary else detail}


def _run_adk() -> dict:
    return _await_blocking(_run_adk_async())


def _run_async() -> dict:
    """Long-running-async leg: publish the research work items to the bus and
    return immediately — the background consumer seals records as it drains,
    and the page's 2s poll shows the chain grow. Pub/Sub when configured;
    the in-process bus otherwise (same interface, keyless-green). The dispatch
    path is sealed INSIDE each record's params (run_mode async / async-local)."""
    from agents import fleet  # deferred (google-adk import)
    from glassbox import work

    bus = work.get_bus()
    bus.start_consumer(work.execute_work_item)
    run_mode = "async" if bus.mode == "pubsub" else "async-local"
    for vendor in list(fleet.MOCK_VENDORS):
        bus.publish({"tool": "research_vendor", "args": {"vendor_name": vendor}, "run_mode": run_mode})
    return {
        "mode": run_mode,
        "detail": f"3 work items published to the {bus.mode} bus; the chain grows as the consumer completes them",
    }


@app.post("/run")
def run_fleet(mode: str = "") -> JSONResponse:
    if not _run_lock.acquire(blocking=False):
        return JSONResponse({"mode": "busy", "detail": "a run is already in progress"}, status_code=409)
    try:
        from glassbox import work

        # The default click must always produce the full seven-record arc,
        # refusal beat included — that narrative IS the demo. The async bus is
        # a real Pub/Sub path but it publishes work items and returns before
        # the chain grows, so it is opt-in via ?mode=async only. (Regression
        # caught 2026-08-27: setting GOOGLE_CLOUD_PROJECT for Firestore flipped
        # the bus to pubsub, which silently made async the default and left a
        # judge's first click showing an empty chain.)
        if mode == "async":
            result = _run_async()
        elif not _have_model_credentials():
            result = _run_direct()
        elif not _model_budget_available():
            result = _run_direct(why=f"daily model budget of {MODEL_RUNS_PER_DAY} runs reached")
        else:
            _model_budget["used"] += 1
            try:
                result = _run_adk()
            except Exception as e:  # honest fallback, loudly labeled
                result = _run_direct(why="ADK path unavailable")
                result["detail"] += f" (adk path failed: {e})"
        result["at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        _last_run.update(result)
        return JSONResponse(result)
    except Exception as e:
        detail = f"run failed: {e}"
        _last_run.update({"mode": "error", "detail": detail})
        return JSONResponse({"mode": "error", "detail": detail}, status_code=500)
    finally:
        _run_lock.release()


def main() -> None:
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))


if __name__ == "__main__":
    main()
