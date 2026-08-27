"""Glass-Box Fleet — hello-fleet slice: orchestrator + research worker.

Every tool action emits a sealed evidence record via glassbox.seal.emit_record.
Vendor data is mock/canned by design (no live scraping; the evidence layer is the product).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.adk.agents import Agent  # noqa: E402
from google.adk.models.google_llm import Gemini  # noqa: E402
from google.adk.tools.agent_tool import AgentTool  # noqa: E402
from google.genai import types  # noqa: E402

from glassbox.seal import emit_record  # noqa: E402
from glassbox import otel  # noqa: E402

# One model per agent, and deliberately not the same one. The free tier meters
# `generateContent` per project PER MODEL, so three agents on three models draw
# three separate daily buckets instead of racing for one — the demo stays
# runnable on a project with no billing account attached at all. It also
# matches the work: cheap lookups for research, a stronger model where the
# mandate decision and the replan actually happen.
MODEL_ORCHESTRATOR = os.environ.get("MODEL_ORCHESTRATOR", "gemini-3.7-flash")
MODEL_RESEARCH = os.environ.get("MODEL_RESEARCH", "gemini-3.5-flash-lite")
MODEL_INTENT = os.environ.get("MODEL_INTENT", "gemini-3.6-flash")

# Thinking off where the model allows it. The demo's work is tool calls against
# a known procurement flow — no reasoning budget needed — and a thinking first
# call measured ~25s, which reads as a hung page on a cold start.
#
# It is not universally allowed. Measured 2026-08-27 against the live API:
# gemini-3.7-flash accepts thinking_budget=0, while gemini-3.6-flash and
# gemini-3.5-flash-lite reject it with a bare `400 INVALID_ARGUMENT` that names
# no field — so an unconditional config silently kills the whole model path and
# the run falls back to `direct`. Opt in per model rather than assume.
THINKING_OPTIONAL = {"gemini-3.7-flash", "gemini-3.5-flash"}


def gen_config(model: str) -> types.GenerateContentConfig:
    if model in THINKING_OPTIONAL:
        return types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    return types.GenerateContentConfig()


# Retry transient model failures at the HTTP layer, not by re-running the agent.
# This matters more here than in an ordinary app: every tool call seals a record
# the instant it happens, so a mid-run 503 that gets retried by replaying the
# errand would seal the research beats a second time and leave a chain with six
# lookups in it. Observed exactly that — a live `503 UNAVAILABLE: this model is
# currently experiencing high demand` landed after the three research records
# were already sealed. Retrying the request underneath the run keeps the
# evidence a faithful account of one errand.
RETRY_OPTIONS = types.HttpRetryOptions(
    attempts=4,
    initial_delay=1.0,
    max_delay=8.0,
    exp_base=2.0,
    http_status_codes=[429, 500, 502, 503, 504],
)


def build_model(name: str) -> Gemini:
    return Gemini(model=name, retry_options=RETRY_OPTIONS)

MOCK_VENDORS = {
    "acme-cloud": {"product": "Object storage", "unit_price_usd": 21.0, "sla": "99.9%"},
    "initech-io": {"product": "Object storage", "unit_price_usd": 19.5, "sla": "99.5%"},
    "globex-data": {"product": "Object storage", "unit_price_usd": 24.0, "sla": "99.95%"},
}

# "" for LLM-orchestrated runs. The UI's keyless demo path sets "direct" so the
# marker lands INSIDE the sealed params — which run mode produced a record is
# itself evidence, not display state. Not a tool argument (keeps the schema
# the model sees clean).
RUN_MODE = ""


def research_vendor(vendor_name: str) -> dict:
    """Look up a vendor's offer (canned demo data). Emits a sealed evidence record."""
    with otel.span("tool.research_vendor", agent="research-worker", action="research_vendor") as _s:
        offer = MOCK_VENDORS.get(vendor_name, {"error": "unknown vendor"})
        params = {"vendor": vendor_name, "offer": offer}
        if RUN_MODE:
            params["run_mode"] = RUN_MODE
        sealed = emit_record("research-worker", "research_vendor", params)
        otel.set_evidence_attributes(_s, sealed)
        inner = sealed.get("record", {})
        return {
            "offer": offer,
            "evidence_record": inner.get("id", "STUB"),
            "record_hash": sealed.get("record_hash", ""),
        }


research_worker = Agent(
    name="research_worker",
    model=build_model(MODEL_RESEARCH),
    generate_content_config=gen_config(MODEL_RESEARCH),
    description="Researches vendor offers for procurement; every lookup is sealed as evidence.",
    instruction=(
        "You research vendors for a procurement flow. The approved vendor list is fixed and is "
        "exactly these three: acme-cloud, initech-io, globex-data. Call research_vendor once for "
        "each of the three — three calls, no more, no fewer — then report every offer factually "
        "in one short table with its evidence record id. Never ask which vendors to research: the "
        "list above IS the list. Do not invent vendors and do not repeat a lookup."
    ),
    tools=[research_vendor],
)

def check_budget_mandate(amount_usd: float) -> dict:
    """Check a monthly spend against the scoped mandate. The check itself is sealed.

    Reads `mandates/demo.json` — the same file the enforcement point in
    issue_purchase_intent reads. One cap, one source of truth: a pre-flight
    check that could disagree with the thing that actually blocks the spend
    would be theatre, and the whole point here is that it isn't."""
    from glassbox import mandate

    with otel.span("tool.check_budget_mandate", agent="intent-worker", action="check_budget_mandate") as _s:
        approved, reason, m = mandate.check(amount_usd)
        limit = float(m.get("cap_usd", 0))
        sealed = emit_record(
            "intent-worker",
            "check_budget_mandate",
            {"amount_usd": amount_usd, "limit_usd": limit, "approved": approved,
             "reason": reason, "mandate_ref": m.get("mandate_id")},
        )
        otel.set_evidence_attributes(_s, sealed)
        return {"approved": approved, "reason": reason, "limit_usd": limit,
                "evidence_record": sealed.get("record", {}).get("id", "STUB")}


def issue_purchase_intent(vendor_name: str, monthly_amount_usd: float) -> dict:
    """Issue a purchase INTENT (no real money moves — evidence demo).

    Enforcement point for the scoped mandate (mandates/demo.json, public
    policy): an over-cap or expired-mandate amount is NEVER executed — the
    refusal itself is sealed as evidence with the mandate reference, and it
    chains exactly like any other record."""
    from glassbox import mandate

    with otel.span("tool.issue_purchase_intent", agent="intent-worker", action="issue_purchase_intent") as _s:
        allowed, reason, m = mandate.check(monthly_amount_usd)
        if not allowed:
            sealed = emit_record(
                "intent-worker",
                "purchase_intent.REFUSED",
                {"vendor": vendor_name, "requested": monthly_amount_usd,
                 "cap": m.get("cap_usd"), "mandate_ref": m.get("mandate_id"),
                 "reason": reason},
            )
            otel.set_evidence_attributes(_s, sealed)
            return {"status": "REFUSED", "reason": reason,
                    "evidence_record": sealed.get("record", {}).get("id", "STUB")}
        sealed = emit_record(
            "intent-worker",
            "issue_purchase_intent",
            {"vendor": vendor_name, "amount_usd": monthly_amount_usd,
             "mandate_ref": m.get("mandate_id")},
        )
        otel.set_evidence_attributes(_s, sealed)
        return {"status": "issued", "intent_id": sealed.get("record", {}).get("id", "STUB"),
                "evidence_record": sealed.get("record", {}).get("id", "STUB")}


def file_expense_record(intent_id: str, vendor_name: str, amount_usd: float) -> dict:
    """File the expense entry for an issued intent. Sealed."""
    with otel.span("tool.file_expense_record", agent="intent-worker", action="file_expense_record") as _s:
        sealed = emit_record(
            "intent-worker",
            "file_expense_record",
            {"intent_id": intent_id, "vendor": vendor_name, "amount_usd": amount_usd},
        )
        otel.set_evidence_attributes(_s, sealed)
        return {"status": "filed", "evidence_record": sealed.get("record", {}).get("id", "STUB")}


intent_worker = Agent(
    name="intent_worker",
    model=build_model(MODEL_INTENT),
    generate_content_config=gen_config(MODEL_INTENT),
    description="Issues purchase intents under a budget mandate; every step sealed as evidence.",
    instruction=(
        "You handle purchase intents in a procurement evidence demo. For a chosen vendor and a "
        "requested monthly amount: (1) call check_budget_mandate for that amount; (2) call "
        "issue_purchase_intent for it — attempt it even when the check said no, because the "
        "refusal is the evidence the demo exists to produce; (3) if the intent comes back "
        "REFUSED, never retry the same amount — instead reduce the seat count to the largest "
        "whole number whose monthly total fits under the cap the refusal reported, and issue "
        "that instead; (4) call file_expense_record with the issued intent_id. Report the "
        "refusal plainly in your summary, with its evidence record id — an agent that was told "
        "no, and can prove it, is the result being demonstrated."
    ),
    tools=[check_budget_mandate, issue_purchase_intent, file_expense_record],
)

# Workers are exposed as TOOLS, not as `sub_agents`. With `sub_agents` the ADK
# `transfer_to_agent` call hands over control: the worker becomes the active
# agent, answers the user directly, and the orchestrator's task context does not
# travel with it. Observed live — the research worker took over, replied "I
# require the specific list of vendor names", transferred back, and the run
# ended after the research beats with no budget check, no refusal and no
# expense. AgentTool keeps the orchestrator in control for the whole errand and
# forces it to state the request explicitly on each delegation, which is also
# what makes the hand-offs legible in the evidence chain.
root_agent = Agent(
    name="procurement_orchestrator",
    model=build_model(MODEL_ORCHESTRATOR),
    generate_content_config=gen_config(MODEL_ORCHESTRATOR),
    description="Orchestrates the procurement fleet; delegates research and purchasing to workers.",
    instruction=(
        "You run a procurement evidence demo, and you stay in charge for the whole errand — "
        "never hand the conversation to a worker, call them as tools and use what they return.\n"
        "When asked to procure storage for a number of seats, do all four steps in one run:\n"
        "(1) Call research_worker with the request 'Research all three approved vendors and "
        "report their unit prices and SLAs.' It returns three offers.\n"
        "(2) Pick the best offer on price and SLA, and say why in one line.\n"
        "(3) Multiply that vendor's unit price by the seat count you were asked for to get the "
        "monthly total. Do NOT shrink the order to fit any budget — order what was asked for and "
        "let the mandate answer.\n"
        "(4) Call intent_worker with a request naming the chosen vendor, the seat count, that "
        "vendor's unit price, and the full monthly total — for example: 'Vendor initech-io, 400 "
        "seats at 19.5/seat, monthly total 7800.0. Budget-check it, attempt the intent, and if "
        "it is refused reduce the seats to what fits and file the expense.'\n"
        "Finish with a short table plus the record ids. If a refusal happened, say so plainly — "
        "it is the result this demo exists to produce, not a failure."
    ),
    tools=[AgentTool(research_worker), AgentTool(intent_worker)],
)
