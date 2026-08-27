"""Async work dispatch for the fleet — Pub/Sub when configured, in-process otherwise.

Track leg: "long-running asynchronous operations". The orchestrator publishes
work items; a background consumer executes the worker tool calls; the UI's
existing 2-second poll shows the evidence chain grow as items complete.

Local-first contract (binding, same pattern as otel.py): with no
GOOGLE_CLOUD_PROJECT, no credentials, or no google-cloud-pubsub package, the
bus degrades to an in-process queue.Queue + daemon consumer thread with the
SAME interface — local runs and tests stay green with zero GCP dependencies.
Topic/subscription creation is guarded and lazy; nothing GCP happens at import.
"""
from __future__ import annotations

import json
import os
import queue
import threading
from typing import Callable, Optional

TOPIC = "glassbox-work"
SUBSCRIPTION = "glassbox-work-sub"

# A work item is a plain dict: {"tool": <name>, "args": {...}, "run_mode": <str>}.
Handler = Callable[[dict], None]


class LocalBus:
    """In-process fallback: queue.Queue + one daemon consumer thread."""

    mode = "local"

    def __init__(self) -> None:
        self._q: "queue.Queue[dict]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None

    def publish(self, item: dict) -> None:
        self._q.put(item)

    def start_consumer(self, handler: Handler) -> None:
        if self._thread and self._thread.is_alive():
            return

        def loop() -> None:
            while True:
                item = self._q.get()
                try:
                    handler(item)
                except Exception:
                    pass  # a failed item must not kill the consumer
                finally:
                    self._q.task_done()

        self._thread = threading.Thread(target=loop, name="glassbox-local-consumer", daemon=True)
        self._thread.start()

    def drain(self, timeout_s: float = 30.0) -> bool:
        """Test/AC helper: block until the queue empties (local bus only)."""
        import time

        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self._q.unfinished_tasks == 0:
                return True
            time.sleep(0.05)
        return False


class PubSubBus:
    """Google Cloud Pub/Sub bus. Constructor raises unless the project is set,
    the package imports, and both clients + topic/subscription set up — callers
    use `get_bus()`, which falls back to LocalBus on ANY failure."""

    mode = "pubsub"

    def __init__(self) -> None:
        project = os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        if not project:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT unset")
        from google.api_core.exceptions import AlreadyExists
        from google.cloud import pubsub_v1

        self._publisher = pubsub_v1.PublisherClient()
        self._subscriber = pubsub_v1.SubscriberClient()
        self._topic_path = self._publisher.topic_path(project, TOPIC)
        self._sub_path = self._subscriber.subscription_path(project, SUBSCRIPTION)
        try:
            self._publisher.create_topic(name=self._topic_path)
        except AlreadyExists:
            pass
        try:
            self._subscriber.create_subscription(
                name=self._sub_path, topic=self._topic_path
            )
        except AlreadyExists:
            pass

    def publish(self, item: dict) -> None:
        self._publisher.publish(self._topic_path, json.dumps(item).encode("utf-8"))

    def start_consumer(self, handler: Handler) -> None:
        def callback(message) -> None:
            try:
                handler(json.loads(message.data.decode("utf-8")))
                message.ack()
            except Exception:
                message.nack()

        self._subscriber.subscribe(self._sub_path, callback=callback)


_bus: Optional[object] = None
_bus_lock = threading.Lock()


def get_bus():
    """Lazy singleton: Pub/Sub if it fully constructs, else the local bus."""
    global _bus
    with _bus_lock:
        if _bus is None:
            try:
                _bus = PubSubBus()
            except Exception:
                _bus = LocalBus()
        return _bus


def execute_work_item(item: dict) -> None:
    """Consumer-side executor: dispatch one work item to a fleet tool.

    Runs on the single consumer thread, so setting fleet.RUN_MODE around the
    call is race-free; the item's run_mode lands INSIDE the sealed params —
    which dispatch path produced a record is evidence, not display state.
    Unknown tools are ignored loudly-by-evidence: nothing is sealed for them.
    """
    from agents import fleet

    tools = {
        "research_vendor": fleet.research_vendor,
        "check_budget_mandate": fleet.check_budget_mandate,
        "issue_purchase_intent": fleet.issue_purchase_intent,
        "file_expense_record": fleet.file_expense_record,
    }
    fn = tools.get(item.get("tool", ""))
    if fn is None:
        return
    fleet.RUN_MODE = str(item.get("run_mode", ""))
    try:
        fn(**item.get("args", {}))
    finally:
        fleet.RUN_MODE = ""
