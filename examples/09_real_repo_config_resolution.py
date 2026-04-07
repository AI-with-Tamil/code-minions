"""
Example 09 — Real Repo Spec Run
================================
Runs Minion against this repo in an isolated git worktree with a real model.

This is the first real "use our product on ourselves" example.
It targets a concrete SDK gap already documented in the repo:
config-file resolution in Minion.

Usage:
    uv run python examples/09_real_repo_config_resolution.py
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from pydantic import BaseModel

from minion import AgentNode, Blueprint, DeterministicNode, EscalationResult, Minion, RunContext, Task
from minion._internal.env import load_env_file
from minion.environments import GitWorktreeEnv
from minion.tools import CODE_TOOLS, SHELL_TOOLS


class RepoSpecState(BaseModel):
    branch: str = ""
    acceptance_passed: bool = False
    acceptance_output: str = ""


def _choose_model() -> str:
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


repo_spec_blueprint = Blueprint(
    name="real_repo_spec",
    state_cls=RepoSpecState,
    nodes=[
        DeterministicNode("capture_branch", fn=capture_branch),
        AgentNode(
            "implement",
            system_prompt=(
                "You are modifying the Minion SDK in its own repository.\n\n"
                "TASK: {task.description}\n\n"
                "ACCEPTANCE CRITERIA: {task.acceptance}\n\n"
                "CONSTRAINTS:\n{task.constraints_list}\n\n"
                "CONTEXT FILES:\n{task.context_list}\n\n"
                "Operate narrowly. Change only the files needed for this task. "
                "After you implement the behavior and add or update tests, stop exploring. "
                "Call done(summary, files_changed) immediately once the acceptance criteria should pass. "
                "Do not continue iterating after the implementation is complete."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=32,
            token_budget=24_000,
        ),
        DeterministicNode("verify", fn=verify_acceptance),
        AgentNode(
            "fix_acceptance",
            system_prompt=(
                "The acceptance command failed. Fix the implementation and tests until "
                "`{task.acceptance}` passes. Do not widen scope. "
                "When the failure is fixed, call done(summary, files_changed) immediately."
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


async def main() -> None:
    model = _choose_model()
    repo_root = Path(__file__).resolve().parents[1]

    task = Task(
        description=(
            "Implement the documented Minion configuration resolution order in src/minion/core/minion.py: "
            "constructor args override config files, then minion.toml, then pyproject.toml [tool.minion], "
            "then environment variables, then SDK defaults. Add tests that prove the precedence."
        ),
        context=[
            "src/minion/core/minion.py",
            "tests/test_core.py",
            "docs/api/08_minion.md",
        ],
        acceptance="uv run pytest -q tests/test_core.py -k ConfigurationResolution",
        constraints=[
            "Do not modify MCP files",
            "Do not change unrelated examples",
            "Keep the public API shape intact",
            "Prefer the smallest implementation that satisfies the documented contract",
        ],
    )

    env = GitWorktreeEnv(
        repo_path=str(repo_root),
        base_branch="main",
        branch_prefix="minion-real",
        cleanup_on_complete=False,
    )

    result = await Minion(
        model=model,
        blueprint=repo_spec_blueprint,
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
