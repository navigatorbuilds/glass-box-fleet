"""OpenTelemetry wiring for the fleet — every run traces in Cloud Trace.

The differentiator this powers: each span carries the sealed evidence record's
id + hash, so standards telemetry (Cloud Trace) and the offline-verifiable
audit log point at the SAME events.

Local-first contract (binding): with no GOOGLE_CLOUD_PROJECT or no Google
credentials, everything here degrades to an in-process no-op — spans are
created against a provider with NO exporter attached (zero network, zero
errors). A missing opentelemetry install degrades further to a null shim.
LOCAL RUNS MUST NOT BREAK; tracing is additive.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator, Optional

_initialized = False
_export_enabled = False
_tracer = None


class _NullSpan:
    """Shim span for environments without opentelemetry installed."""

    def set_attribute(self, _key: str, _value) -> None:
        return None


def _try_enable_gcp_export(provider) -> bool:
    """Attach the Cloud Trace exporter iff a project is configured and the
    exporter can be constructed. Any failure (no creds, no package, no
    network) leaves the provider exporter-less — spans stay local no-ops."""
    project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
    if not project:
        return False
    try:
        from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        exporter = CloudTraceSpanExporter(project_id=project)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        return True
    except Exception:
        return False


def init_tracing() -> bool:
    """Idempotent tracer setup. Returns True iff Cloud Trace export is live."""
    global _initialized, _export_enabled, _tracer
    if _initialized:
        return _export_enabled
    _initialized = True
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider

        provider = TracerProvider(
            resource=Resource.create({"service.name": "glass-box-fleet"})
        )
        _export_enabled = _try_enable_gcp_export(provider)
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("glass-box-fleet")
    except Exception:
        _tracer = None  # opentelemetry absent/broken → null shim below
        _export_enabled = False
    return _export_enabled


@contextmanager
def span(name: str, **attributes) -> Iterator[object]:
    """Open a span carrying `attributes`; yields the span so callers can add
    evidence attributes (record_id / record_hash) once sealing returns.
    Total-graceful: never raises from tracing itself."""
    init_tracing()
    if _tracer is None:
        yield _NullSpan()
        return
    with _tracer.start_as_current_span(name) as s:
        for key, value in attributes.items():
            try:
                s.set_attribute(key, value)
            except Exception:
                pass
        yield s


def set_evidence_attributes(s: object, sealed: Optional[dict]) -> None:
    """Stamp the sealed record's id + hash onto a span — the trace↔evidence tie."""
    if not sealed:
        return
    try:
        record = sealed.get("record", {}) or {}
        s.set_attribute("evidence.record_id", record.get("id", ""))
        s.set_attribute("evidence.record_hash", sealed.get("record_hash", ""))
    except Exception:
        pass
