"""Trace — append-only execution trace for a Minion run."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class TraceEvent:
    type: str          # node_start | node_complete | node_skip | tool_call | tool_result | log | ...
    node: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Trace:
    run_id: str
    events: list[TraceEvent] = field(default_factory=list)
    listeners: list[Callable[[TraceEvent], None]] = field(default_factory=list, repr=False)

    def record(self, event_type: str, node: str, **data: Any) -> None:
        event = TraceEvent(
            type=event_type,
            node=node,
            timestamp=time.time(),
            data=data,
        )
        self.events.append(event)
        for listener in list(self.listeners):
            listener(event)

    def record_skip(self, node: str) -> None:
        self.record("node_skip", node)

    def record_node_start(self, node: str) -> None:
        self.record("node_start", node)

    def record_node_complete(self, node: str, **data: Any) -> None:
        self.record("node_complete", node, **data)

    def record_tool_call(self, node: str, tool: str, args: dict[str, Any]) -> None:
        self.record("tool_call", node, tool=tool, args=args)

    def record_tool_result(self, node: str, tool: str, result: str | None, error: str | None) -> None:
        self.record("tool_result", node, tool=tool, result=result, error=error)

    def record_log(self, node: str, message: str) -> None:
        self.record("log", node, message=message)

    # --- Query helpers ---

    def by_type(self, event_type: str) -> list[TraceEvent]:
        """Return all events of the given type."""
        return [e for e in self.events if e.type == event_type]

    def by_node(self, node: str) -> list[TraceEvent]:
        """Return all events for the given node."""
        return [e for e in self.events if e.node == node]

    def tool_calls(self, name: str | None = None) -> list[TraceEvent]:
        """Return tool_call events, optionally filtered to a specific tool name."""
        events = [e for e in self.events if e.type == "tool_call"]
        if name is not None:
            events = [e for e in events if e.data.get("tool") == name]
        return events
