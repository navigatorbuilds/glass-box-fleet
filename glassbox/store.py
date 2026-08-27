"""Durable evidence persistence — Firestore mirror of the sealed record log.

Why: `evidence/records.jsonl` is EPHEMERAL on Cloud Run (in-memory filesystem,
reset on cold start / new revision). Firestore keeps the full chain across
revisions so a judge never watches history vanish.

Local-first contract (binding, same pattern as otel.py / work.py): the mirror
activates ONLY when `FIRESTORE=1` is set AND the client constructs (project
from GOOGLE_CLOUD_PROJECT, default elara-agentic). Local/keyless runs keep the
jsonl file as the single source with zero GCP dependencies; a failed client
construction degrades to disabled with one stderr note. Writes NEVER break
sealing (guarded); the stored document is the sealed envelope VERBATIM — no
schema drift vs the sealer output.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import uuid
from typing import Optional

COLLECTION = "records"

# One run id per server process; documents key run_id/seq so ordering survives
# interleaved revisions (global order = created ts, then run_id/seq tiebreak).
RUN_ID = uuid.uuid4().hex[:12]

_client = None
_client_tried = False
_seq = 0
_lock = threading.Lock()


def enabled() -> bool:
    return os.environ.get("FIRESTORE", "") == "1"


def _get_client():
    """Lazy, once-only client construction; never raises to callers."""
    global _client, _client_tried
    with _lock:
        if _client_tried:
            return _client
        _client_tried = True
        try:
            from google.cloud import firestore

            project = os.environ.get("GOOGLE_CLOUD_PROJECT", "elara-agentic").strip()
            _client = firestore.Client(project=project)
        except Exception as e:
            print(f"glassbox.store: FIRESTORE=1 but client unavailable ({e}); "
                  f"falling back to jsonl only", file=sys.stderr)
            _client = None
        return _client


def append(sealed: dict) -> None:
    """Mirror one sealed envelope to Firestore. Guarded: sealing never breaks."""
    global _seq
    if not enabled():
        return
    client = _get_client()
    if client is None:
        return
    try:
        with _lock:
            _seq += 1
            seq = _seq
        doc = {
            "run_id": RUN_ID,
            "seq": seq,
            "created": time.time(),
            "sealed": sealed,  # the envelope verbatim — no schema drift
        }
        client.collection(COLLECTION).document(f"{RUN_ID}-{seq:06d}").set(doc)
    except Exception as e:
        print(f"glassbox.store: append failed ({e}); jsonl remains authoritative locally",
              file=sys.stderr)


def read_all() -> Optional[list[dict]]:
    """Full sealed-envelope history in chain order, or None when the mirror is
    off/unavailable (callers then read the local jsonl)."""
    if not enabled():
        return None
    client = _get_client()
    if client is None:
        return None
    try:
        docs = (
            client.collection(COLLECTION)
            .order_by("created")
            .order_by("run_id")
            .order_by("seq")
            .stream()
        )
        return [d.to_dict().get("sealed", {}) for d in docs]
    except Exception as e:
        print(f"glassbox.store: read failed ({e}); falling back to jsonl", file=sys.stderr)
        return None
