"""Minion — the runner. Ties model, blueprint, and environment together."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any, Callable

from minion._internal.engine import _NodeAbort, _NodeEscalate, execute_blueprint
from minion.core.blueprint import Blueprint
from minion.core.context import RunConfig, RunContext
from minion.core.result import EscalationResult, RunResult
from minion.core.state import RunState
from minion.core.task import Task, coerce_task
from minion.events import MinionEvent
from minion.trace import Trace, TraceEvent


class ConfigurationError(Exception):
    """Raised when Minion cannot resolve its configuration."""


class Minion:
    """The runner. Entry point users interact with.

    Ties model, blueprint, and environment together.
    """

    def __init__(
        self,
        model: str | object = "claude-sonnet-4-6",
        blueprint: str | Blueprint = "coding",
        environment: str | object = "local",
        config: RunConfig | None = None,
        storage: str | None = None,
        max_concurrent: int = 1,
    ) -> None:
        self._model_spec = model
        self._blueprint_spec = blueprint
        self._environment_spec = environment
        self._config = config or RunConfig()
        self._storage = storage
        self._max_concurrent = max_concurrent
        self._hooks: dict[MinionEvent, list[Callable]] = {}

    def on(self, event: MinionEvent) -> Callable:
        """Decorator to register event hooks."""
        def decorator(fn: Callable) -> Callable:
            self._hooks.setdefault(event, []).append(fn)
            return fn
        return decorator

    async def _emit(self, event: MinionEvent, **data: Any) -> None:
        for hook in self._hooks.get(event, []):
            result = hook(data)
            if asyncio.iscoroutine(result):
                await result

    def _trace_listener(
        self,
        queue: asyncio.Queue[dict[str, Any]] | None = None,
    ) -> Callable[[TraceEvent], None]:
        def listener(event: TraceEvent) -> None:
            payload = {
                "type": event.type,
                "node": event.node,
                "timestamp": event.timestamp,
                "data": event.data,
            }
            if queue is not None:
                queue.put_nowait(payload)

            mapped = {
                "node_start": MinionEvent.NODE_START,
                "node_complete": MinionEvent.NODE_COMPLETE,
                "node_skip": MinionEvent.NODE_SKIP,
                "tool_call": MinionEvent.TOOL_CALL,
                "tool_result": MinionEvent.TOOL_RESULT,
                "agent_done": MinionEvent.AGENT_DONE,
                "judge_veto": MinionEvent.ESCALATION,
            }.get(event.type)
            if mapped is not None:
                asyncio.create_task(self._emit(mapped, **payload))

        return listener

    def _resolve_model(self) -> object:
        if isinstance(self._model_spec, str):
            return _resolve_model_string(self._model_spec)
        return self._model_spec

    def _resolve_blueprint(self) -> Blueprint:
        if isinstance(self._blueprint_spec, str):
            return _resolve_blueprint_string(self._blueprint_spec)
        return self._blueprint_spec

    def _resolve_environment(self) -> object:
        if isinstance(self._environment_spec, str):
            return _resolve_environment_string(self._environment_spec)
        return self._environment_spec

    async def _run_internal(
        self,
        task: str | Task,
        event_queue: asyncio.Queue[dict[str, Any]] | None = None,
    ) -> RunResult:
        task_obj = coerce_task(task)
        model = self._resolve_model()
        blueprint = self._resolve_blueprint()
        env = self._resolve_environment()

        # Validate blueprint
        blueprint.validate()

        # Setup environment if needed
        if hasattr(env, "setup"):
            await env.setup()

        run_id = uuid.uuid4().hex[:12]
        trace = Trace(run_id=run_id)
        trace.listeners.append(self._trace_listener(event_queue))

        # Construct state
        state_cls = blueprint.state_cls or RunState
        state = state_cls()

        ctx = RunContext(
            env=env,
            state=state,
            trace=trace,
            model=model,
            config=self._config,
            task=task_obj,
            run_id=run_id,
            node="",
        )

        await self._emit(MinionEvent.RUN_START, run_id=run_id, task=task_obj)

        start_time = time.monotonic()
        outcome: str = "passed"
        escalation_info: dict[str, str] | None = None
        diff = ""
        working_dir = _result_working_dir(env)

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
        except Exception as e:
            outcome = "failed"
            trace.record("run_error", "", error=str(e))
        finally:
            try:
                diff_result = await env.exec("git diff")
                diff = diff_result.stdout
            except Exception:
                pass
            # Cleanup environment
            if hasattr(env, "cleanup"):
                try:
                    await env.cleanup()
                except Exception:
                    pass

        duration_ms = int((time.monotonic() - start_time) * 1000)

        # Calculate total tokens from trace
        total_tokens = sum(
            e.data.get("input_tokens", 0) + e.data.get("output_tokens", 0)
            for e in trace.events
        )

        # Get branch from state
        branch = getattr(state, "branch", None)

        # Get summary from last agent_done event
        summary = ""
        for event in reversed(trace.events):
            if event.type == "agent_done":
                summary = event.data.get("summary", "")
                break

        await self._emit(MinionEvent.RUN_COMPLETE,
                         run_id=run_id, outcome=outcome)

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
                working_dir=working_dir,
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
            working_dir=working_dir,
        )

    async def run(self, task: str | Task) -> RunResult:
        """Execute a single task. Primary async entry point."""
        return await self._run_internal(task)

    def run_sync(self, task: str | Task) -> RunResult:
        """Sync convenience wrapper."""
        return asyncio.run(self.run(task))

    async def run_stream(self, task: str | Task) -> AsyncIterator[dict[str, Any]]:
        """Streaming — yields events as they happen."""
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        task_runner = asyncio.create_task(self._run_internal(task, event_queue=queue))

        while True:
            if task_runner.done() and queue.empty():
                break
            try:
                event = await asyncio.wait_for(queue.get(), timeout=0.05)
                yield event
            except asyncio.TimeoutError:
                continue

        await task_runner

    async def run_batch(self, tasks: list[str | Task]) -> list[RunResult]:
        """Run tasks in parallel up to max_concurrent."""
        sem = asyncio.Semaphore(self._max_concurrent)

        async def bounded_run(t: str | Task) -> RunResult:
            async with sem:
                return await self.run(t)

        return await asyncio.gather(*[bounded_run(t) for t in tasks])


def _resolve_model_string(spec: str) -> object:
    """Resolve a model string shorthand to a model instance."""
    if spec.startswith("claude") or spec.startswith("anthropic"):
        from minion.models.claude import ClaudeModel
        return ClaudeModel(model=spec)
    if spec.startswith("gpt") or spec.startswith("openai"):
        from minion.models.openai import OpenAIModel
        return OpenAIModel(model=spec)

    # Auto-detect from env
    if os.environ.get("ANTHROPIC_API_KEY"):
        from minion.models.claude import ClaudeModel
        return ClaudeModel(model=spec)
    if os.environ.get("OPENAI_API_KEY"):
        from minion.models.openai import OpenAIModel
        return OpenAIModel(model=spec)

    raise ConfigurationError(
        f"Cannot resolve model '{spec}'. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
        f"or pass an explicit model instance."
    )


def _resolve_blueprint_string(spec: str) -> Blueprint:
    """Resolve a blueprint string shorthand."""
    if spec == "coding":
        from minion.blueprints.coding import coding_blueprint
        return coding_blueprint
    raise ConfigurationError(
        f"Unknown blueprint '{spec}'. Use 'coding' or pass a Blueprint instance."
    )


def _resolve_environment_string(spec: str) -> object:
    """Resolve an environment string shorthand."""
    if spec == "local":
        from minion.environments.local import LocalEnv
        return LocalEnv(".")
    if spec == "worktree":
        from minion.environments.worktree import GitWorktreeEnv
        return GitWorktreeEnv(repo_path=".")
    if spec == "docker":
        from minion.environments.docker import DockerEnv
        return DockerEnv(image="python:3.12", repo_path=".")
    raise ConfigurationError(
        f"Unknown environment '{spec}'. Use 'local', 'worktree', 'docker', "
        f"or pass an environment instance."
    )


def _result_working_dir(env: object) -> str | None:
    if hasattr(env, "repo_path"):
        return getattr(env, "repo_path")
    if hasattr(env, "path"):
        return getattr(env, "path")
    return None
