"""BlueprintEngine — executes a Blueprint against a RunContext."""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass
from typing import Any

from minion._internal.loop import run_agent_loop
from minion.core.blueprint import Blueprint
from minion.core.context import RunContext
from minion.core.node import (
    AgentNode,
    AnyNode,
    DeterministicNode,
    JudgeNode,
    LoopNode,
    ParallelNode,
)
class _NodeAbort(Exception):
    """Internal: node triggered abort."""


class _NodeEscalate(Exception):
    """Internal: node triggered escalation."""
    def __init__(self, node: str, reason: str, last_failure: str = "") -> None:
        self.node = node
        self.reason = reason
        self.last_failure = last_failure


@dataclass
class AgentExecution:
    completed: bool
    exhausted_rounds: bool = False


async def execute_blueprint(
    blueprint: Blueprint,
    ctx: RunContext,
) -> None:
    """Execute all nodes in order. Modifies ctx.state in place.

    Raises _NodeEscalate if a node escalates.
    Raises _NodeAbort if a node aborts.
    """
    for node in blueprint.nodes:
        await _execute_node(node, ctx, blueprint)


async def _execute_node(
    node: AnyNode,
    ctx: RunContext,
    blueprint: Blueprint,
) -> None:
    """Execute a single node, handling condition, failure policy, etc."""
    # Check condition
    condition = getattr(node, "condition", None)
    if condition is not None and not condition(ctx):
        ctx.trace.record_skip(node.name)
        return

    # Set current node
    prev_node = ctx.node
    ctx.node = node.name
    ctx.trace.record_node_start(node.name)

    try:
        if isinstance(node, DeterministicNode):
            await _run_deterministic(node, ctx)
        elif isinstance(node, AgentNode):
            await _run_agent(node, ctx)
        elif isinstance(node, JudgeNode):
            await _run_judge(node, ctx, blueprint)
        elif isinstance(node, ParallelNode):
            await _run_parallel(node, ctx, blueprint)
        elif isinstance(node, LoopNode):
            await _run_loop(node, ctx)
        else:
            raise TypeError(f"Unknown node type: {type(node)}")

        ctx.trace.record_node_complete(node.name)

    except (_NodeAbort, _NodeEscalate):
        raise
    except Exception as e:
        on_failure = getattr(node, "on_failure", "escalate")
        if on_failure == "abort":
            ctx.trace.record_node_complete(node.name, error=str(e))
            raise _NodeAbort() from e
        elif on_failure == "escalate":
            ctx.trace.record_node_complete(node.name, error=str(e))
            raise _NodeEscalate(
                node=node.name,
                reason=f"Node '{node.name}' failed: {e}",
                last_failure=str(e),
            ) from e
        else:  # continue
            ctx.trace.record_node_complete(node.name, error=str(e), continued=True)
    finally:
        ctx.node = prev_node


async def _run_deterministic(node: DeterministicNode, ctx: RunContext) -> None:
    result = node.fn(ctx)
    if inspect.isawaitable(result):
        await result


async def _run_agent(
    node: AgentNode,
    ctx: RunContext,
    veto_reason: str | None = None,
) -> AgentExecution:
    rounds = getattr(ctx, "_agent_rounds", None)
    if rounds is None:
        rounds = {}
        setattr(ctx, "_agent_rounds", rounds)

    current_rounds = rounds.get(node.name, 0)
    if current_rounds >= node.max_rounds:
        ctx.trace.record(
            "agent_max_rounds",
            node.name,
            max_rounds=node.max_rounds,
            on_max_rounds=node.on_max_rounds,
        )
        if node.on_max_rounds == "continue":
            return AgentExecution(completed=False, exhausted_rounds=True)
        if node.on_max_rounds == "abort":
            raise _NodeAbort()
        raise _NodeEscalate(
            node=node.name,
            reason=f"AgentNode '{node.name}' exceeded max_rounds={node.max_rounds}",
            last_failure="max_rounds exhausted",
        )

    rounds[node.name] = current_rounds + 1
    loop_result = await run_agent_loop(
        ctx=ctx,
        system_prompt=node.system_prompt,
        tools=node.tools,
        max_iterations=node.max_iterations,
        token_budget=node.token_budget,
        veto_reason=veto_reason,
    )

    # Store done() results on state if applicable
    if loop_result.files_changed and hasattr(ctx.state, "files_changed"):
        ctx.state.files_changed = loop_result.files_changed

    if loop_result.exhausted:
        raise RuntimeError(
            f"AgentNode '{node.name}' exhausted budget/iterations without calling done()"
        )

    return AgentExecution(completed=True)


async def _run_judge(
    node: JudgeNode,
    ctx: RunContext,
    blueprint: Blueprint,
) -> None:
    """Run judge evaluation. On veto, may re-enter the target AgentNode."""
    # Find the target AgentNode
    target: AgentNode | None = None
    for n in blueprint.nodes:
        if isinstance(n, AgentNode) and n.name == node.evaluates:
            target = n
            break
        if isinstance(n, ParallelNode):
            for child in n.nodes:
                if isinstance(child, AgentNode) and child.name == node.evaluates:
                    target = child
                    break

    if target is None:
        raise ValueError(
            f"JudgeNode '{node.name}': evaluates='{node.evaluates}' "
            f"but no AgentNode with that name found"
        )

    # Get the diff for the judge to evaluate
    diff_result = await ctx.exec("git diff")
    diff = diff_result.stdout

    # Get agent summary from trace
    agent_summary = ""
    for event in reversed(ctx.trace.events):
        if event.type == "agent_done" and event.node == node.evaluates:
            agent_summary = event.data.get("summary", "")
            break

    vetoes = 0
    while vetoes < node.max_vetoes:
        # Ask the judge
        judge_prompt = (
            f"You are a code review judge. Evaluate the following change.\n\n"
            f"TASK: {ctx.task.description}\n\n"
            f"CRITERIA:\n{node.criteria}\n\n"
            f"AGENT SUMMARY: {agent_summary}\n\n"
            f"DIFF:\n{diff}\n\n"
            f"Respond with exactly one of:\n"
            f"- APPROVE\n"
            f"- VETO: <reason>\n"
        )

        judge_response = await ctx.ask(judge_prompt, max_tokens=1024)
        judge_response = judge_response.strip()

        if judge_response.upper().startswith("APPROVE"):
            ctx.trace.record("judge_approve", node.name)
            # Write verdict to state if the state has a verdict field
            _write_verdict(ctx, node.name, "approved")
            return

        # Veto
        veto_reason = judge_response
        if ":" in veto_reason:
            veto_reason = veto_reason.split(":", 1)[1].strip()
        vetoes += 1

        ctx.trace.record("judge_veto", node.name,
                         reason=veto_reason, veto_number=vetoes)
        _write_verdict(ctx, node.name, f"vetoed: {veto_reason}")

        if node.on_veto == "retry" and vetoes < node.max_vetoes:
            # Re-enter the target agent with veto reason
            prev_node = ctx.node
            ctx.node = target.name
            ctx.trace.record_node_start(target.name)
            try:
                retry_result = await _run_agent(target, ctx, veto_reason=veto_reason)
                ctx.trace.record_node_complete(target.name)
            finally:
                ctx.node = prev_node

            if retry_result.exhausted_rounds:
                return

            # Re-fetch diff for next judge round
            diff_result = await ctx.exec("git diff")
            diff = diff_result.stdout
        elif node.on_veto == "escalate":
            raise _NodeEscalate(
                node=node.name,
                reason=f"Judge vetoed: {veto_reason}",
                last_failure=veto_reason,
            )
        elif node.on_veto == "continue":
            return

    # Max vetoes exhausted
    if node.on_veto == "retry":
        # Retry was the policy but we ran out — escalate
        raise _NodeEscalate(
            node=node.name,
            reason=f"Judge vetoed {vetoes} times (max_vetoes={node.max_vetoes})",
            last_failure=veto_reason,
        )


def _write_verdict(ctx: RunContext, judge_name: str, verdict: str) -> None:
    """Write judge verdict to state if a matching field exists."""
    # Try common patterns: security_verdict, correctness_verdict, etc.
    # Also try: {judge_name}_verdict removing _council suffix
    field_candidates = []
    for part in judge_name.split("_"):
        field_candidates.append(f"{part}_verdict")
    field_candidates.append(f"{judge_name}_verdict")
    field_candidates.append(judge_name.replace("_council", "_verdict"))

    for field_name in field_candidates:
        if hasattr(ctx.state, field_name):
            setattr(ctx.state, field_name, verdict)
            return


async def _run_parallel(
    node: ParallelNode,
    ctx: RunContext,
    blueprint: Blueprint,
) -> None:
    """Run child nodes concurrently."""
    async def run_child(child: AnyNode) -> None:
        await _execute_node(child, ctx, blueprint)

    results = await asyncio.gather(
        *[run_child(child) for child in node.nodes],
        return_exceptions=True,
    )

    # Check for failures
    errors = [r for r in results if isinstance(r, Exception)]
    if errors:
        # Re-raise the first escalation or abort
        for e in errors:
            if isinstance(e, _NodeEscalate):
                raise e
            if isinstance(e, _NodeAbort):
                raise e
        # Otherwise apply ParallelNode's on_failure
        first_error = errors[0]
        if node.on_failure == "abort":
            raise _NodeAbort() from first_error
        elif node.on_failure == "escalate":
            raise _NodeEscalate(
                node=node.name,
                reason=f"ParallelNode '{node.name}' child failed: {first_error}",
                last_failure=str(first_error),
            ) from first_error
        # else: continue


async def _run_loop(node: LoopNode, ctx: RunContext) -> None:
    """Run sub-blueprint for each item."""
    items = node.iterate_over(ctx)
    max_iter = node.max_iterations or len(items)

    for i, item in enumerate(items):
        if i >= max_iter:
            break

        # Bind per-item state
        node.bind(ctx, item)

        # Run the sub-blueprint
        try:
            await execute_blueprint(node.sub_blueprint, ctx)
        except _NodeEscalate as e:
            if node.on_failure == "abort":
                raise _NodeAbort() from e
            elif node.on_failure == "escalate":
                raise
            # else: continue — move to next item
        except _NodeAbort:
            raise
        except Exception as e:
            if node.on_failure == "abort":
                raise _NodeAbort() from e
            elif node.on_failure == "escalate":
                raise _NodeEscalate(
                    node=node.name,
                    reason=f"LoopNode '{node.name}' iteration {i} failed: {e}",
                    last_failure=str(e),
                ) from e
            # else: continue
