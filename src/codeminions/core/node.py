"""Node types — the building blocks of a Blueprint."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal

if TYPE_CHECKING:
    from codeminions.core.context import RunContext
    from codeminions.core.tool import Tool


# Type aliases
ConditionFn = Callable[["RunContext"], bool] | None
NodeFn = Callable[["RunContext"], Awaitable[None] | None]


@dataclass
class DeterministicNode:
    """Pure Python node. No LLM. Always runs the same way."""
    name: str
    fn: NodeFn
    condition: ConditionFn = None
    on_failure: Literal["abort", "continue", "escalate"] = "escalate"


@dataclass
class AgentNode:
    """LLM loop with tool calling. Runs until done() is called or budget exhausted."""
    name: str
    system_prompt: str
    tools: list["Tool"] = field(default_factory=list)
    condition: ConditionFn = None
    max_iterations: int = 80
    token_budget: int = 50_000
    max_rounds: int = 1
    on_max_rounds: Literal["escalate", "abort", "continue"] = "escalate"
    on_failure: Literal["abort", "continue", "escalate"] = "escalate"


@dataclass
class JudgeNode:
    """LLM evaluates the output of a prior AgentNode. Can veto + retry."""
    name: str
    evaluates: str      # name of AgentNode to evaluate
    criteria: str
    on_veto: Literal["retry", "escalate", "continue"] = "retry"
    max_vetoes: int = 2


@dataclass
class ParallelNode:
    """Runs multiple child nodes concurrently. Merges state on completion."""
    name: str
    nodes: list[DeterministicNode | AgentNode | JudgeNode]
    on_failure: Literal["abort", "continue", "escalate"] = "escalate"


@dataclass
class LoopNode:
    """Iterates a sub-blueprint over a discovered list of targets."""
    name: str
    sub_blueprint: Any  # Blueprint — forward ref to avoid circular import
    iterate_over: Callable[["RunContext"], list[Any]]
    bind: Callable[["RunContext", Any], None]
    max_iterations: int | None = None
    on_failure: Literal["abort", "continue", "escalate"] = "continue"


# Union of all node types
AnyNode = DeterministicNode | AgentNode | JudgeNode | ParallelNode | LoopNode
