"""MinionEvent — event types emitted during a run."""

from __future__ import annotations

from enum import Enum


class MinionEvent(str, Enum):
    RUN_START = "run_start"
    RUN_COMPLETE = "run_complete"
    NODE_START = "node_start"
    NODE_COMPLETE = "node_complete"
    NODE_SKIP = "node_skip"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    AGENT_DONE = "agent_done"
    ESCALATION = "escalation"
