"""
Example Real 02 — Self-Hosted Task Queue
========================================
Runs a small queue of real SDK tasks against this repo in isolated git worktrees.

Example type:
- Real example
- Sequential dogfood workflow
- Supports file- and folder-scoped tasks

Usage:
    uv run python examples/real/02_self_hosted_task_queue.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from pydantic import BaseModel

from codeminions import AgentNode, Blueprint, DeterministicNode, EscalationResult, Minion, RunContext, Task
from codeminions._internal.env import load_env_file
from codeminions.environments import GitWorktreeEnv
from codeminions.tools import CODE_TOOLS, SHELL_TOOLS


class QueueState(BaseModel):
    branch: str = ""
    acceptance_passed: bool = False
    acceptance_output: str = ""


def choose_model() -> str:
    load_env_file(Path.cwd() / ".env")
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_TOKEN"):
        return "claude-sonnet-4-6"
    if os.environ.get("OPENAI_API_KEY"):
        return "gpt-4o"
    raise RuntimeError("No model credentials found in environment or .env")


async def capture_branch(ctx: RunContext) -> None:
    result = await ctx.exec("git branch --show-current")
    ctx.state.branch = result.stdout.strip()


async def verify_acceptance(ctx: RunContext) -> None:
    result = await ctx.exec(ctx.task.acceptance)
    ctx.state.acceptance_passed = result.exit_code == 0
    ctx.state.acceptance_output = (result.stdout + result.stderr).strip()
    if not ctx.state.acceptance_passed:
        ctx.log(ctx.state.acceptance_output)


queue_blueprint = Blueprint(
    name="self_hosted_task_queue",
    state_cls=QueueState,
    nodes=[
        DeterministicNode("capture_branch", fn=capture_branch),
        AgentNode(
            "implement",
            system_prompt=(
                "You are modifying CodeMinions in its own repository.\n\n"
                "TASK: {task.description}\n\n"
                "ACCEPTANCE CRITERIA: {task.acceptance}\n\n"
                "CONSTRAINTS:\n{task.constraints_list}\n\n"
                "CONTEXT PATHS:\n{task.context_list}\n\n"
                "Context paths may be files or folders. Stay inside the intended subsystem unless the task forces otherwise.\n"
                "Operate narrowly. Change only the files required for this task. "
                "Call done(summary, files_changed) immediately once the implementation should satisfy acceptance."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=36,
            token_budget=28_000,
        ),
        DeterministicNode("verify", fn=verify_acceptance),
        AgentNode(
            "fix_acceptance",
            system_prompt=(
                "The acceptance command failed. Fix the implementation and tests until "
                "`{task.acceptance}` passes. Respect the task constraints and context scope. "
                "When fixed, call done(summary, files_changed) immediately."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: not ctx.state.acceptance_passed,
            max_rounds=2,
            on_max_rounds="escalate",
            max_iterations=24,
            token_budget=18_000,
        ),
    ],
)


def build_tasks() -> list[Task]:
    return [
        Task(
            description=(
                "Tighten the examples directory guidance so it documents research, validation, and real examples clearly."
            ),
            context=[
                "examples/",
                "README.md",
            ],
            acceptance="uv run pytest -q tests/test_examples_contracts.py",
            constraints=[
                "Do not change the SDK public API",
                "Keep edits limited to examples and related docs",
            ],
        ),
        Task(
            description=(
                "Improve the real-run documentation so the paths and terminology match the current example layout."
            ),
            context=[
                "docs/",
                "examples/validation/",
                "examples/real/",
            ],
            acceptance="uv run pytest -q tests/test_examples_contracts.py -k repo_spec",
            constraints=[
                "Do not widen scope beyond docs and example layout consistency",
                "Do not modify MCP files",
            ],
        ),
    ]


async def run_one(repo_root: Path, model: str, task: Task, index: int) -> None:
    env = GitWorktreeEnv(
        repo_path=str(repo_root),
        base_branch="main",
        branch_prefix=f"codeminions-real-queue-{index}",
        cleanup_on_complete=False,
    )

    result = await Minion(
        model=model,
        blueprint=queue_blueprint,
        environment=env,
    ).run(task)

    print(f"\n=== TASK {index} ===")
    print(f"description : {task.description}")
    print(f"outcome     : {result.outcome}")
    print(f"branch      : {result.branch}")
    print(f"worktree    : {env.path}")
    print(f"tokens      : {result.tokens}")
    print(f"duration    : {result.duration_ms}ms")
    print(f"acceptance  : {getattr(result.state, 'acceptance_passed', False)}")
    print(f"summary     : {result.summary}")

    if isinstance(result, EscalationResult):
        print(f"escalated   : {result.reason}")

    print("--- diff ---")
    print(result.diff.strip() or "<no diff>")

    output = getattr(result.state, "acceptance_output", "")
    if output:
        print("--- acceptance output ---")
        print(output)

    if result.outcome != "passed":
        raise RuntimeError(f"Task {index} failed or escalated; stopping queue")


async def main() -> None:
    model = choose_model()
    repo_root = Path(__file__).resolve().parents[2]
    tasks = build_tasks()

    print(f"model : {model}")
    print(f"tasks : {len(tasks)}")

    for i, task in enumerate(tasks, start=1):
        await run_one(repo_root=repo_root, model=model, task=task, index=i)


if __name__ == "__main__":
    asyncio.run(main())
