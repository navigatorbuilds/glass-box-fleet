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
    record = emit_record("research-worker", "research_vendor", {"vendor": vendor_name, "offer": offer})
    return {"offer": offer, "evidence_record": record.get("record_id", "STUB")}


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

root_agent = Agent(
    name="procurement_orchestrator",
    model="gemini-3.5-flash",
    description="Orchestrates the procurement fleet; delegates research to workers.",
    instruction=(
        "You run a procurement evidence demo. When asked to compare storage vendors, delegate "
        "research on acme-cloud, initech-io and globex-data to the research worker, then "
        "summarize the offers in a table and recommend one on price+SLA. Keep it brief."
    ),
    sub_agents=[research_worker],
)
