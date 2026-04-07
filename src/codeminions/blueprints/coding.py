"""coding_blueprint — the default built-in blueprint (Stripe pattern)."""

from __future__ import annotations

from pydantic import BaseModel

from codeminions.core.blueprint import Blueprint
from codeminions.core.context import RunContext
from codeminions.core.node import AgentNode, DeterministicNode
from codeminions.tools import CODE_TOOLS, SHELL_TOOLS


class CodingState(BaseModel):
    branch: str = ""
    context_summary: str = ""
    lint_failed: bool = False
    lint_output: str = ""
    tests_failed: bool = False
    test_output: str = ""
    files_changed: list[str] = []
    pr_url: str = ""


async def _create_branch(ctx: RunContext) -> None:
    ctx.state.branch = f"codeminions/{ctx.run_id[:8]}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")


async def _gather_context(ctx: RunContext) -> None:
    result = await ctx.exec("git log --oneline -10")
    parts = [result.stdout]
    # Pre-read task.context files so the agent doesn't waste tokens fetching basics
    for path in ctx.task.context:
        try:
            content = await ctx.read(path)
            parts.append(f"--- {path} ---\n{content}")
        except (FileNotFoundError, Exception):
            parts.append(f"--- {path} (not found) ---")
    ctx.state.context_summary = "\n\n".join(parts)


async def _run_lint(ctx: RunContext) -> None:
    result = await ctx.exec("ruff check . --fix")
    ctx.state.lint_failed = result.exit_code != 0
    ctx.state.lint_output = result.stdout


async def _run_tests(ctx: RunContext) -> None:
    result = await ctx.exec("pytest tests/ -x --tb=short")
    ctx.state.tests_failed = result.exit_code != 0
    ctx.state.test_output = result.stdout


async def _commit(ctx: RunContext) -> None:
    await ctx.exec("git add -A")
    await ctx.exec('git commit -m "minion: complete task"')


async def _push(ctx: RunContext) -> None:
    await ctx.exec(f"git push -u origin {ctx.state.branch}")


async def _create_pr(ctx: RunContext) -> None:
    result = await ctx.exec(
        f'gh pr create --title "minion: {ctx.task.description[:72]}" '
        f'--body "Automated by CodeMinions\\n\\nTask: {ctx.task.description}" '
        f'--head {ctx.state.branch}'
    )
    ctx.state.pr_url = result.stdout.strip()


coding_blueprint = Blueprint(
    name="coding",
    state_cls=CodingState,
    nodes=[
        DeterministicNode("create_branch", fn=_create_branch),
        DeterministicNode("gather_context", fn=_gather_context),
        AgentNode(
            "implement",
            system_prompt=(
                "You are an expert software engineer working in an isolated environment.\n"
                "Recent git history and task context are in ctx.state.context_summary.\n"
                "Complete the task fully. Write production-quality code.\n"
                "Call done() when finished."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=80,
            token_budget=60_000,
        ),
        DeterministicNode("lint", fn=_run_lint),
        AgentNode(
            "fix_lint",
            system_prompt=(
                "Fix the lint errors below. Do not change anything else.\n\n"
                "LINT OUTPUT:\n{state.lint_output}"
            ),
            tools=CODE_TOOLS,
            condition=lambda ctx: ctx.state.lint_failed,
            max_iterations=20,
            token_budget=15_000,
            max_rounds=1,
        ),
        DeterministicNode("test", fn=_run_tests),
        AgentNode(
            "fix_tests",
            system_prompt=(
                "Fix the failing tests below. Do not change unrelated code.\n\n"
                "TEST OUTPUT:\n{state.test_output}"
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: ctx.state.tests_failed,
            max_iterations=40,
            token_budget=30_000,
            max_rounds=2,
            on_max_rounds="escalate",
        ),
        DeterministicNode("commit", fn=_commit),
        DeterministicNode("push", fn=_push),
        DeterministicNode("create_pr", fn=_create_pr),
    ],
)
