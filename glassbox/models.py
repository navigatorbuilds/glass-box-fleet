"""Model assignment — one place, because two files need it and only one may import ADK.

`agents/fleet.py` builds the agents from these names; `ui/server.py` advertises them
on /agents. The UI must stay serveable with no model credentials and no ADK import at
request time, so it cannot reach the names through fleet.py — and a hand-copied mirror
drifts (it did: the registry still said gemini-3.5-flash for all three agents after the
per-agent split, and shipped that to the one page whose job is transparency).

One model per agent, and deliberately not the same one. The free tier meters
`generateContent` per project PER MODEL, so three agents on three models draw three
separate daily buckets instead of racing for one — the demo stays runnable on a project
with no billing account attached at all. It also matches the work: cheap lookups for
research, a stronger model where the mandate decision and the replan actually happen.
"""
from __future__ import annotations

import os

MODEL_ORCHESTRATOR = os.environ.get("MODEL_ORCHESTRATOR", "gemini-3.7-flash")
MODEL_RESEARCH = os.environ.get("MODEL_RESEARCH", "gemini-3.5-flash-lite")
MODEL_INTENT = os.environ.get("MODEL_INTENT", "gemini-3.6-flash")
