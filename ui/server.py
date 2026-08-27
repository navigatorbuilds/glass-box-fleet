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

import html
import json
import os
import sys
import threading
import time
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


def read_rows() -> list[dict]:
    """Parse the evidence log into display rows with a continuity badge.

    Badge semantics (display-level): OK = this record's signed prev pointer
    equals the previous sealed record's hash; BROKEN = it does not (or the
    line is unparseable); STUB = an unsigned placeholder row from the
    pre-sealer wiring — loud, red, never presentable.
    """
    rows: list[dict] = []
    if not RUN_LOG.exists():
        return rows
    expected_prev = GENESIS_PREV
    for i, raw in enumerate(RUN_LOG.read_text().splitlines()):
        raw = raw.strip()
        if not raw:
            continue
        try:
            line = json.loads(raw)
        except json.JSONDecodeError:
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
        return '<tr><td colspan="6" class="empty">no records yet — POST /run (or the Run button) to grow the chain</td></tr>'
    out = []
    for r in rows:
        badge_class = {"OK": "ok", "BROKEN": "broken", "STUB": "stub"}[r["badge"]]
        out.append(
            "<tr>"
            f'<td>{r["index"]}</td>'
            f'<td>{html.escape(r["agent"])}</td>'
            f'<td>{html.escape(r["action"])}{" <em>(direct)</em>" if r["mode"] == "direct" else ""}</td>'
            f'<td>{html.escape(r["ts"])}</td>'
            f'<td class="mono">{html.escape(r["record_id"])}</td>'
            f'<td><span class="badge {badge_class}">{r["badge"]}</span></td>'
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
<thead><tr><th>#</th><th>agent</th><th>action</th><th>ts</th><th>record id</th><th>chain</th></tr></thead>
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
    records = []
    if RUN_LOG.exists():
        for raw in RUN_LOG.read_text().splitlines():
            raw = raw.strip()
            if raw:
                try:
                    records.append(json.loads(raw))
                except json.JSONDecodeError:
                    records.append({"UNPARSEABLE_LINE": raw})
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


def _have_model_credentials() -> bool:
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        return True
    adc = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
    return adc.exists()


def _run_direct() -> dict:
    """Keyless demo path: exercise the sealed research tool directly so the
    chain grows without any LLM. Rows are marked "direct" via params."""
    from agents import fleet  # deferred: pulls google-adk, never at page load

    sealed_ids = []
    fleet.RUN_MODE = "direct"
    try:
        for vendor in list(fleet.MOCK_VENDORS):
            result = fleet.research_vendor(vendor)
            sealed_ids.append(result.get("evidence_record", "?"))
    finally:
        fleet.RUN_MODE = ""
    return {"mode": "direct", "detail": f"research_vendor x{len(sealed_ids)} (no model credentials — sealed via direct tool calls)"}


def _run_adk() -> dict:
    from agents.fleet import root_agent  # deferred import
    from google.adk.runners import InMemoryRunner

    runner = InMemoryRunner(agent=root_agent)
    events = runner.run_debug("Procure object storage for the team within the monthly budget.", quiet=True)
    return {"mode": "adk", "detail": f"{len(events)} events"}


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

        if mode == "async" or (mode == "" and _have_model_credentials() and work.get_bus().mode == "pubsub"):
            result = _run_async()
        elif _have_model_credentials():
            try:
                result = _run_adk()
            except Exception as e:  # honest fallback, loudly labeled
                result = _run_direct()
                result["detail"] += f" (adk path failed: {e})"
        else:
            result = _run_direct()
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
