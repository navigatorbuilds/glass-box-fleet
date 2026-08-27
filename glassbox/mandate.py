"""Scoped mandate for the intent worker — the demo's enforcement policy.

The mandate is PUBLIC POLICY, committed at `mandates/demo.json` (it is what the
fleet is allowed to do, not a secret). Enforcement lives in the purchase-intent
tool: an over-cap amount is never executed; the REFUSAL itself is sealed as a
hash-linked evidence record, exactly like any approved action.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Tuple

MANDATE_PATH = Path(__file__).resolve().parent.parent / "mandates" / "demo.json"

_cached: Optional[dict] = None


def get_mandate() -> dict:
    global _cached
    if _cached is None:
        _cached = json.loads(MANDATE_PATH.read_text())
    return _cached


def check(amount: float) -> Tuple[bool, str, dict]:
    """(allowed, reason, mandate). Reasons: ok | exceeds_mandate_cap | mandate_expired."""
    m = get_mandate()
    expires = m.get("expires", "")
    if expires:
        expiry_s = time.mktime(time.strptime(expires, "%Y-%m-%dT%H:%M:%SZ"))
        if time.time() > expiry_s:
            return False, "mandate_expired", m
    if amount > float(m.get("cap_eur", 0)):
        return False, "exceeds_mandate_cap", m
    return True, "ok", m
