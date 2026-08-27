"""Glass-Box Fleet — hello-fleet slice: orchestrator + research worker.

Every tool action emits a sealed evidence record via glassbox.seal.emit_record.
Vendor data is mock/canned by design (no live scraping; the evidence layer is the product).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.adk.agents import Agent  # noqa: E402
from google.genai import types  # noqa: E402

from glassbox.seal import emit_record  # noqa: E402
from glassbox import otel  # noqa: E402

MODEL = "gemini-3.5-flash"

# Thinking off. The demo's work is tool calls against a scripted procurement
# flow — no reasoning budget needed — and a thinking first call measured ~25s,
# which reads as a hung page on a Cloud Run cold start. Every agent shares this.
GEN_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_budget=0)
)

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
    model=MODEL,
    generate_content_config=GEN_CONFIG,
    description="Researches vendor offers for procurement; every lookup is sealed as evidence.",
    instruction=(
        "You research vendors for a procurement flow. Use the research_vendor tool for each "
        "vendor the orchestrator names. Report offers factually; do not invent vendors."
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
    model=MODEL,
    generate_content_config=GEN_CONFIG,
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

root_agent = Agent(
    name="procurement_orchestrator",
    model=MODEL,
    generate_content_config=GEN_CONFIG,
    description="Orchestrates the procurement fleet; delegates research and purchasing to workers.",
    instruction=(
        "You run a procurement evidence demo. When asked to procure storage for a number of "
        "seats: (1) delegate research on acme-cloud, initech-io and globex-data to the research "
        "worker — exactly one lookup per vendor, three in total; (2) pick the best offer on "
        "price+SLA and say why in one line; (3) multiply that vendor's unit price by the "
        "requested seat count to get the monthly total; (4) delegate to the intent worker to "
        "budget-check, issue the purchase intent for that total, and file the expense. Do not "
        "pre-emptively shrink the order to fit a budget — order what was asked for and let the "
        "mandate answer. Keep the final summary to a short table plus the record ids."
    ),
    sub_agents=[research_worker, intent_worker],
)
