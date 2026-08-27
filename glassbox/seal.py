"""Evidence emission: every fleet action goes through here.

Calls the Rust `sealer` (built on the published elara-record crate) to produce a signed,
hash-linked record. Until the sealer binary lands, falls back to an UNSIGNED-STUB entry so
the fleet wiring can be built end-to-end; the stub is loudly marked and never presentable.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

from glassbox import otel
from glassbox import store

EVIDENCE_DIR = Path(os.environ.get("GLASSBOX_EVIDENCE_DIR", "evidence"))
SEALER_BIN = os.environ.get("GLASSBOX_SEALER", "sealer/target/release/sealer")
RUN_LOG = EVIDENCE_DIR / "records.jsonl"


def emit_record(agent: str, action: str, params: dict) -> dict:
    """Seal one action event; returns the signed record (or a marked stub).

    Wrapped in an OTel span so the sealer subprocess cost is visible in Cloud
    Trace and the span carries the resulting record id + hash (trace↔evidence
    tie). Tracing is a no-op locally without credentials."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    event = {
        "agent": agent,
        "action": action,
        "params": params,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with otel.span("sealer.emit_record", agent=agent, action=action) as s:
        sealer = Path(SEALER_BIN)
        if sealer.exists():
            out = subprocess.run(
                [str(sealer)],
                input=json.dumps(event),
                capture_output=True,
                text=True,
                timeout=30,
                # Chain continuity without caller-held state: the sealer reads the
                # last sealed line of the run log and links the new record to it.
                env={**os.environ, "SEALER_PREV_FROM": str(RUN_LOG)},
            )
            if out.returncode != 0:
                raise RuntimeError(f"sealer failed: {out.stderr.strip()}")
            record = json.loads(out.stdout)
            otel.set_evidence_attributes(s, record)
        else:
            record = {"UNSIGNED_STUB": True, "event": event}
    with RUN_LOG.open("a") as f:
        f.write(json.dumps(record) + "\n")
    if "UNSIGNED_STUB" not in record:
        # Durable mirror (Cloud Run's FS is ephemeral); guarded no-op locally.
        store.append(record)
    return record
