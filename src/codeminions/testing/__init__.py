"""Testing utilities — test blueprints without real API calls."""

from __future__ import annotations

import uuid
import time
from typing import TYPE_CHECKING

from codeminions._internal.engine import _NodeAbort, _NodeEscalate, execute_blueprint
from codeminions.core.context import RunConfig, RunContext
from codeminions.core.result import EscalationResult, RunResult
from codeminions.core.state import RunState
from codeminions.core.task import coerce_task
from codeminions.models._base import ModelResponse, ToolCall
from codeminions.testing.mock_env import MockCommandNotFoundError, MockEnvironment
from codeminions.testing.mock_model import MockExhaustedError, MockModel
from codeminions.trace import Trace

if TYPE_CHECKING:
    from codeminions.core.blueprint import Blueprint
    from codeminions.core.task import Task


async def run_blueprint_test(
    blueprint: "Blueprint",
    task: str | "Task",
    model: MockModel,
    env: MockEnvironment,
) -> RunResult:
    """Run a blueprint with mock model and environment. No real API calls."""
    task_obj = coerce_task(task)

    blueprint.validate()

    run_id = uuid.uuid4().hex[:12]
    trace = Trace(run_id=run_id)

    state_cls = blueprint.state_cls or RunState
    state = state_cls()

    ctx = RunContext(
        env=env,
        state=state,
        trace=trace,
        model=model,
        config=RunConfig(),
        task=task_obj,
        run_id=run_id,
        node="",
    )

    start_time = time.monotonic()
    outcome = "passed"
    escalation_info: dict[str, str] | None = None

    try:
        await execute_blueprint(blueprint, ctx)
    except _NodeEscalate as e:
        outcome = "escalated"
        escalation_info = {
            "node": e.node,
            "reason": e.reason,
            "last_failure": e.last_failure,
        }
    except _NodeAbort:
        outcome = "failed"
    except Exception:
        outcome = "failed"

    duration_ms = int((time.monotonic() - start_time) * 1000)

    branch = getattr(state, "branch", None)

    summary = ""
    for event in reversed(trace.events):
        if event.type == "agent_done":
            summary = event.data.get("summary", "")
            break

    diff = ""
    total_tokens = sum(
        e.data.get("input_tokens", 0) + e.data.get("output_tokens", 0)
        for e in trace.events
    )

    if escalation_info:
        return EscalationResult(
            run_id=run_id,
            outcome="escalated",
            branch=branch,
            diff=diff,
            summary=summary,
            state=state,
            trace=trace,
            tokens=total_tokens,
            duration_ms=duration_ms,
            working_dir=getattr(env, "path", None),
            node=escalation_info["node"],
            reason=escalation_info["reason"],
            last_failure=escalation_info["last_failure"],
        )

    return RunResult(
        run_id=run_id,
        outcome=outcome,
        branch=branch,
        diff=diff,
        summary=summary,
        state=state,
        trace=trace,
        tokens=total_tokens,
        duration_ms=duration_ms,
        working_dir=getattr(env, "path", None),
    )


__all__ = [
    "MockModel",
    "MockEnvironment",
    "MockExhaustedError",
    "MockCommandNotFoundError",
    "ModelResponse",
    "ToolCall",
    "run_blueprint_test",
]
