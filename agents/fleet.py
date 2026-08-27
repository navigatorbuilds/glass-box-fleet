"""Glass-Box Fleet — hello-fleet slice: orchestrator + research worker.

Every tool action emits a sealed evidence record via glassbox.seal.emit_record.
Vendor data is mock/canned by design (no live scraping; the evidence layer is the product).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google.adk.agents import Agent  # noqa: E402

from glassbox.seal import emit_record  # noqa: E402

MOCK_VENDORS = {
    "acme-cloud": {"product": "Object storage", "unit_price_usd": 21.0, "sla": "99.9%"},
    "initech-io": {"product": "Object storage", "unit_price_usd": 19.5, "sla": "99.5%"},
    "globex-data": {"product": "Object storage", "unit_price_usd": 24.0, "sla": "99.95%"},
}


def research_vendor(vendor_name: str) -> dict:
    """Look up a vendor's offer (canned demo data). Emits a sealed evidence record."""
    offer = MOCK_VENDORS.get(vendor_name, {"error": "unknown vendor"})
    sealed = emit_record("research-worker", "research_vendor", {"vendor": vendor_name, "offer": offer})
    inner = sealed.get("record", {})
    return {
        "offer": offer,
        "evidence_record": inner.get("id", "STUB"),
        "record_hash": sealed.get("record_hash", ""),
    }


research_worker = Agent(
    name="research_worker",
    model="gemini-3.5-flash",
    description="Researches vendor offers for procurement; every lookup is sealed as evidence.",
    instruction=(
        "You research vendors for a procurement flow. Use the research_vendor tool for each "
        "vendor the orchestrator names. Report offers factually; do not invent vendors."
    ),
    tools=[research_vendor],
)

BUDGET_LIMIT_USD = 500.0


def check_budget_mandate(amount_usd: float) -> dict:
    """Check a spend amount against the demo mandate budget. The check itself is sealed."""
    approved = amount_usd <= BUDGET_LIMIT_USD
    sealed = emit_record(
        "intent-worker",
        "check_budget_mandate",
        {"amount_usd": amount_usd, "limit_usd": BUDGET_LIMIT_USD, "approved": approved},
    )
    return {"approved": approved, "limit_usd": BUDGET_LIMIT_USD,
            "evidence_record": sealed.get("record", {}).get("id", "STUB")}


def issue_purchase_intent(vendor_name: str, monthly_amount_usd: float) -> dict:
    """Issue a purchase INTENT (no real money moves — evidence demo). Sealed; refused over budget."""
    if monthly_amount_usd > BUDGET_LIMIT_USD:
        sealed = emit_record(
            "intent-worker",
            "purchase_intent_REFUSED",
            {"vendor": vendor_name, "amount_usd": monthly_amount_usd,
             "reason": f"exceeds mandate budget {BUDGET_LIMIT_USD}"},
        )
        return {"status": "REFUSED", "reason": "over mandate budget",
                "evidence_record": sealed.get("record", {}).get("id", "STUB")}
    sealed = emit_record(
        "intent-worker",
        "issue_purchase_intent",
        {"vendor": vendor_name, "amount_usd": monthly_amount_usd},
    )
    return {"status": "issued", "intent_id": sealed.get("record", {}).get("id", "STUB"),
            "evidence_record": sealed.get("record", {}).get("id", "STUB")}


def file_expense_record(intent_id: str, vendor_name: str, amount_usd: float) -> dict:
    """File the expense entry for an issued intent. Sealed."""
    sealed = emit_record(
        "intent-worker",
        "file_expense_record",
        {"intent_id": intent_id, "vendor": vendor_name, "amount_usd": amount_usd},
    )
    return {"status": "filed", "evidence_record": sealed.get("record", {}).get("id", "STUB")}


intent_worker = Agent(
    name="intent_worker",
    model="gemini-3.5-flash",
    description="Issues purchase intents under a budget mandate; every step sealed as evidence.",
    instruction=(
        "You handle purchase intents in a procurement evidence demo. For a chosen vendor: first "
        "check_budget_mandate for the monthly amount, then issue_purchase_intent, then "
        "file_expense_record with the returned intent_id. If the mandate check fails or an "
        "intent is REFUSED, report that plainly — the refusal is itself evidence. Never retry "
        "a refused amount."
    ),
    tools=[check_budget_mandate, issue_purchase_intent, file_expense_record],
)

root_agent = Agent(
    name="procurement_orchestrator",
    model="gemini-3.5-flash",
    description="Orchestrates the procurement fleet; delegates research and purchasing to workers.",
    instruction=(
        "You run a procurement evidence demo. When asked to procure storage: (1) delegate "
        "research on acme-cloud, initech-io and globex-data to the research worker; (2) pick "
        "the best offer on price+SLA and say why in one line; (3) delegate to the intent worker "
        "to budget-check, issue the purchase intent and file the expense for the chosen vendor "
        "at its monthly price. Keep the final summary to a short table plus the record ids."
    ),
    sub_agents=[research_worker, intent_worker],
)
