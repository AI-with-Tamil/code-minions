"""
Example Real 01 — Self-Hosted Single Task
=========================================
Runs Minion against this repo in an isolated git worktree on one real SDK task.

Example type:
- Real example
- Self-hosted dogfood workflow
- Folder-aware task context, not limited to single-file edits

Usage:
    uv run python examples/real/01_self_hosted_single_task.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from pydantic import BaseModel

from codeminions import AgentNode, Blueprint, DeterministicNode, EscalationResult, Minion, RunContext, Task
from codeminions._internal.env import load_env_file
from codeminions.environments import GitWorktreeEnv
from codeminions.tools.code import edit_file, read_file, write_file
from codeminions.tools.shell import run_command


class SelfHostedState(BaseModel):
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


self_hosted_blueprint = Blueprint(
    name="self_hosted_single_task",
    state_cls=SelfHostedState,
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
                "Context paths may be files or folders. Start by reading only the listed context paths.\n"
                "Do not browse broadly through the repository.\n"
                "Operate narrowly. Change only the files required for this task.\n"
                "Use the fewest tools possible: read files, make the smallest edit, run acceptance, finish.\n"
                "Run the acceptance command yourself before finishing.\n"
                "You must call the done tool to finish this task.\n"
                "As soon as the acceptance command passes, call done(summary, files_changed) immediately.\n"
                "Do not continue exploring or polishing after acceptance passes."
            ),
            tools=[read_file, edit_file, write_file, run_command],
            max_iterations=28,
            token_budget=24_000,
        ),
        DeterministicNode("verify", fn=verify_acceptance),
        AgentNode(
            "fix_acceptance",
            system_prompt=(
                "The acceptance command failed. Fix the implementation and tests until "
                "`{task.acceptance}` passes. Do not widen scope beyond the task context. "
                "When fixed, call done(summary, files_changed) immediately."
            ),
            tools=[read_file, edit_file, write_file, run_command],
            condition=lambda ctx: not ctx.state.acceptance_passed,
            max_rounds=2,
            on_max_rounds="escalate",
            max_iterations=24,
            token_budget=18_000,
        ),
    ],
)


def build_task() -> Task:
    return Task(
        description=(
            "Fix the Minion config precedence bug where codeminions.toml currently blocks per-key fallback "
            "to pyproject.toml. Implement merged per-key resolution in src/codeminions/core/minion.py and add "
            "one focused regression test in tests/test_core.py proving that a partial codeminions.toml still "
            "falls back to pyproject.toml for missing keys."
        ),
        context=[
            "src/codeminions/core/minion.py",
            "tests/test_core.py",
            "docs/api/08_minion.md",
        ],
        acceptance="uv run pytest -q tests/test_core.py -k ConfigurationResolution",
        constraints=[
            "Keep the public API unchanged",
            "Do not modify MCP files",
            "Change only src/codeminions/core/minion.py and tests/test_core.py unless absolutely required",
            "Add one focused regression test, not a large new test suite",
        ],
    )


async def main() -> None:
    model = choose_model()
    repo_root = Path(__file__).resolve().parents[2]
    task = build_task()

    env = GitWorktreeEnv(
        repo_path=str(repo_root),
        base_branch="main",
        branch_prefix="codeminions-real-single",
        cleanup_on_complete=False,
    )

    result = await Minion(
        model=model,
        blueprint=self_hosted_blueprint,
        environment=env,
    ).run(task)

    print(f"model      : {model}")
    print(f"outcome    : {result.outcome}")
    print(f"branch     : {result.branch}")
    print(f"worktree   : {env.path}")
    print(f"tokens     : {result.tokens}")
    print(f"duration   : {result.duration_ms}ms")
    print(f"summary    : {result.summary}")
    print(f"acceptance : {getattr(result.state, 'acceptance_passed', False)}")

    if isinstance(result, EscalationResult):
        print(f"escalated  : {result.reason}")

    print("\n--- diff ---")
    print(result.diff.strip() or "<no diff>")

    output = getattr(result.state, "acceptance_output", "")
    if output:
        print("\n--- acceptance output ---")
        print(output)


if __name__ == "__main__":
    asyncio.run(main())
