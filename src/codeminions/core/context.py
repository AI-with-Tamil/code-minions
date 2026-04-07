"""RunContext — the spine of the SDK. ExecResult. RunConfig."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Literal, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from codeminions.core.task import Task
    from codeminions.trace import Trace


EnvT = TypeVar("EnvT")


@dataclass
class ExecResult:
    stdout: str
    stderr: str
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


@dataclass
class RunConfig:
    max_concurrent: int = 1
    token_budget: int = 200_000
    timeout_seconds: int = 3600
    trace_level: Literal["minimal", "full"] = "full"


@dataclass
class RunContext(Generic[EnvT]):
    """Passed to every tool and deterministic node function.

    Carries the environment, shared state, trace, model, config, and task.
    Constructed by the runner — never instantiated by user code.
    """
    env: EnvT
    state: BaseModel
    trace: "Trace"
    model: object        # BaseModelProtocol — kept as object to avoid circular import
    config: RunConfig
    task: "Task"
    run_id: str
    node: str

    # --- Convenience methods (delegate to env) ---

    async def read(self, path: str) -> str:
        return await self.env.read(path)  # type: ignore[union-attr]

    async def write(self, path: str, content: str) -> None:
        await self.env.write(path, content)  # type: ignore[union-attr]

    async def exec(self, cmd: str, cwd: str | None = None) -> ExecResult:
        return await self.env.exec(cmd, cwd=cwd)  # type: ignore[union-attr]

    def log(self, message: str) -> None:
        self.trace.record_log(self.node, message)

    async def ask(self, prompt: str, max_tokens: int = 512) -> str:
        """One-shot LLM call. Does NOT add to agent conversation history."""
        from codeminions.models._base import Message
        resp = await self.model.call(  # type: ignore[union-attr]
            messages=[Message(role="user", content=prompt)],
            tools=[],
            system="You are a helpful assistant. Answer concisely.",
            max_tokens=max_tokens,
        )
        self.trace.record(
            "model_response",
            self.node,
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
            stop_reason=resp.stop_reason,
            one_shot=True,
        )
        return resp.text
