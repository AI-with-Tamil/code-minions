"""
Example 02 — Spotify Judge Pattern
=====================================
LLM-as-judge evaluates agent output before the workflow continues.
Inspired by Spotify Honk: 25% veto rate, 50% self-correction after veto.

Example type:
- Research example
- Pressure test of `JudgeNode` and retry semantics
- Approximation of the Honk pattern inside Minion's ordered blueprint model

Pattern:
    implement → verify_attempt → judge → lint → test → ship

What is directly modeled:
- The judge doesn't fix the code — it only evaluates and rejects
- Agent self-corrects when given the veto reason
- Judge runs BEFORE CI — catches problems cheaply before burning CI budget
- Static, task-focused prompting instead of retrieval-heavy context assembly
- Independent deterministic verification before the judge stage

What is approximated:
- Honk's broader verifier/fleet ecosystem is represented here as deterministic follow-up nodes
- The judge criteria here stand in for Spotify's fuller "does this diff still match the original ask?" workflow
- PR handling is modeled as a deterministic ship step, not a platform control plane

What this example proves:
- JudgeNode is a first-class primitive (not bolted on)
- Veto reason is injected into AgentNode's next attempt automatically
- max_vetoes caps the retry loop
- Clean separation: agent writes code, judge evaluates, deterministic nodes verify
"""

from pydantic import BaseModel

from codeminions import (
    AgentNode,
    Blueprint,
    DeterministicNode,
    JudgeNode,
    Minion,
    RunContext,
)
from codeminions.tools import CODE_TOOLS, SHELL_TOOLS


class CodingState(BaseModel):
    branch: str = ""
    verifier_summary: str = ""
    lint_failed: bool = False
    tests_failed: bool = False
    lint_output: str = ""
    test_output: str = ""
    files_changed: list[str] = []


async def create_branch(ctx: RunContext) -> None:
    ctx.state.branch = f"codeminions/{ctx.run_id[:8]}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")


async def run_lint(ctx: RunContext) -> None:
    result = await ctx.exec("ruff check . --fix")
    ctx.state.lint_failed = result.exit_code != 0
    ctx.state.lint_output = result.stdout


async def run_tests(ctx: RunContext) -> None:
    result = await ctx.exec("pytest tests/ -x --tb=short")
    ctx.state.tests_failed = result.exit_code != 0
    ctx.state.test_output = result.stdout


async def verify_attempt(ctx: RunContext) -> None:
    """
    Deterministic verifier step before the judge.
    This is a lightweight stand-in for richer independent verification systems.
    """
    diff = await ctx.exec("git diff --stat")
    ctx.state.verifier_summary = diff.stdout.strip()


async def push_and_pr(ctx: RunContext) -> None:
    await ctx.exec("git add -A")
    await ctx.exec('git commit -m "minion: complete task"')
    await ctx.exec(f"git push -u origin {ctx.state.branch}")
    await ctx.exec(
        f'gh pr create --title "minion: {ctx.task.description[:72]}" '
        f'--body "Automated by CodeMinions" --head {ctx.state.branch}'
    )


spotify_blueprint = Blueprint(
    name="spotify",
    state_cls=CodingState,
    nodes=[
        DeterministicNode("create_branch", fn=create_branch),

        AgentNode(
            "implement",
            system_prompt=(
                "Complete the task. Stay focused on the original task only. "
                "Do not refactor unrelated code. Do not add unrequested features. "
                "Call done() when finished."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=80,
            token_budget=60_000,
            max_rounds=3,
        ),

        DeterministicNode("verify_attempt", fn=verify_attempt),

        # Judge evaluates the diff from implement.
        # If vetoed: injects veto reason into implement's next attempt.
        # Agent self-corrects ~50% of the time (Spotify data).
        JudgeNode(
            name="judge",
            evaluates="implement",
            criteria=(
                "The diff still matches the original task description exactly. "
                "No unrelated files were modified. "
                "No scope creep — no refactoring, no style changes outside the task. "
                "No commented-out code left behind. "
                "The change is minimal and focused on the original ask."
            ),
            on_veto="retry",
            max_vetoes=2,
        ),

        DeterministicNode("lint", fn=run_lint),

        AgentNode(
            "fix_lint",
            system_prompt="Fix lint errors only. Do not change logic.",
            tools=CODE_TOOLS,
            condition=lambda ctx: ctx.state.lint_failed,
            max_rounds=1,
            token_budget=10_000,
        ),

        DeterministicNode("test", fn=run_tests),

        AgentNode(
            "fix_tests",
            system_prompt="Fix failing tests only.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: ctx.state.tests_failed,
            max_rounds=2,
            on_max_rounds="escalate",
            token_budget=30_000,
        ),

        DeterministicNode("ship", fn=push_and_pr),
    ],
)


async def main():
    result = await Minion(
        model="claude-sonnet-4-6",
        blueprint=spotify_blueprint,
        environment="local",
    ).run("Add request ID header to all API responses")

    print(f"outcome : {result.outcome}")
    print(f"branch  : {result.branch}")
    print(f"tokens  : {result.tokens}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
