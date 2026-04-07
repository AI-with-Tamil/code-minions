"""
Example 01 — Stripe Pattern
============================
The core unattended coding workflow.
Inspired by Stripe Minions: 1,300+ PRs/week, zero human-written code.

Example type:
- Research example
- Pressure test of Minion's ordered deterministic/agent hybrid
- Not a literal reproduction of Stripe's internal system

Pattern:
    gather_context → implement → lint → fix_lint? → test → fix_tests? → commit → push → create_pr

Research pressure being tested:
- gather_context runs deterministically BEFORE the agent starts (MCP tools, links, ticket hydration)
- lint runs locally before push — agent never wastes CI on autoformatter failures
- test autofixes applied deterministically first; only unfixable failures go to the agent
- max 2 CI rounds — hard cap, then escalate
- PR created from template after push — always, deterministically

What is directly modeled:
- deterministic context collection before the agent loop
- alternating deterministic and agentic steps
- bounded repair loops before shipping
- acceptance of "put the LLM in a box" by surrounding it with deterministic stages

What is approximated:
- MCP hydration is represented by deterministic setup work instead of a full external context bus
- branch, push, and PR steps are modeled locally rather than through Stripe's internal platform
- the environment here is kept lightweight so the workflow shape stays visible

What this example proves:
- Blueprint is an ordered list of nodes, not a graph
- DeterministicNode for steps we can anticipate
- AgentNode for steps requiring LLM judgment
- Shared typed state across nodes via ctx.state
- Conditional nodes skip automatically when condition=False
- Bounded retries via max_rounds= with escalation on exhaustion
"""

from pydantic import BaseModel

from codeminions import (
    AgentNode,
    Blueprint,
    DeterministicNode,
    EscalationResult,
    Minion,
    RunContext,
)
from codeminions.tools import CODE_TOOLS, SHELL_TOOLS


# --- Shared state ---

class CodingState(BaseModel):
    branch: str = ""
    context_summary: str = ""         # populated by gather_context
    hydrated_context: list[str] = []
    lint_failed: bool = False
    lint_output: str = ""
    tests_failed: bool = False
    test_output: str = ""
    files_changed: list[str] = []
    pr_url: str = ""


# --- Deterministic node functions ---

async def create_branch(ctx: RunContext) -> None:
    ctx.state.branch = f"codeminions/{ctx.run_id[:8]}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")


async def gather_context(ctx: RunContext) -> None:
    """
    Runs before the agent starts. Hydrates obvious local context from the task.
    This is a Minion-friendly stand-in for richer deterministic hydration over
    tickets, links, and MCP resources before the agent loop begins.
    """
    history = await ctx.exec("git log --oneline -10")
    parts = ["Recent history:\n" + history.stdout.strip()]

    if ctx.task.constraints:
        parts.append("Constraints:\n" + "\n".join(f"- {c}" for c in ctx.task.constraints))

    hydrated: list[str] = []
    for path in ctx.task.context:
        try:
            content = await ctx.read(path)
            hydrated.append(path)
            parts.append(f"Context file: {path}\n{content}")
        except FileNotFoundError:
            parts.append(f"Context file missing: {path}")

    ctx.state.hydrated_context = hydrated
    ctx.state.context_summary = "\n\n".join(part for part in parts if part.strip())


async def run_lint(ctx: RunContext) -> None:
    """Autofix first (ruff --fix), then report what remains."""
    result = await ctx.exec("ruff check . --fix")
    ctx.state.lint_failed = result.exit_code != 0
    ctx.state.lint_output = result.stdout


async def run_tests(ctx: RunContext) -> None:
    """
    Apply autofixes first (e.g. snapshot updates, generated file updates).
    Only set tests_failed for failures that have no autofix.
    Agent only sees what it actually needs to fix.
    """
    await ctx.exec("pytest tests/ --snapshot-update -q")   # apply autofixes
    result = await ctx.exec("pytest tests/ -x --tb=short") # check what remains
    ctx.state.tests_failed = result.exit_code != 0
    ctx.state.test_output = result.stdout


async def commit_changes(ctx: RunContext) -> None:
    await ctx.exec("git add -A")
    await ctx.exec('git commit -m "minion: complete task"')


async def push_branch(ctx: RunContext) -> None:
    await ctx.exec(f"git push -u origin {ctx.state.branch}")


async def create_pr(ctx: RunContext) -> None:
    """Create PR deterministically after push. Always from template."""
    result = await ctx.exec(
        f'gh pr create --title "minion: {ctx.task.description[:72]}" '
        f'--body "Automated by CodeMinions\n\nTask: {ctx.task.description}" '
        f'--head {ctx.state.branch}'
    )
    ctx.state.pr_url = result.stdout.strip()


# --- Blueprint ---

coding_blueprint = Blueprint(
    name="coding",
    state_cls=CodingState,
    nodes=[
        DeterministicNode("create_branch",   fn=create_branch),
        DeterministicNode("gather_context",  fn=gather_context),

        AgentNode(
            "implement",
            system_prompt=(
                "You are an expert software engineer working in an isolated environment.\n"
                "Deterministically hydrated context is in {state.context_summary}.\n"
                "Do the implementation only after using that context.\n"
                "Complete the task fully. Write production-quality code.\n"
                "Call done() when finished."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=80,
            token_budget=60_000,
            max_rounds=2,
        ),

        DeterministicNode("lint", fn=run_lint),

        AgentNode(
            "fix_lint",
            system_prompt="Fix the lint errors shown below. Do not change anything else.",
            tools=CODE_TOOLS,
            condition=lambda ctx: ctx.state.lint_failed,
            max_iterations=20,
            token_budget=15_000,
            max_rounds=1,
        ),

        DeterministicNode("test", fn=run_tests),

        AgentNode(
            "fix_tests",
            system_prompt="Fix the failing tests shown below. Do not change unrelated code.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: ctx.state.tests_failed,
            max_iterations=40,
            token_budget=30_000,
            max_rounds=2,
            on_max_rounds="escalate",
        ),

        DeterministicNode("commit",     fn=commit_changes),
        DeterministicNode("push",       fn=push_branch),
        DeterministicNode("create_pr",  fn=create_pr),
    ],
)


# --- Run ---

async def main():
    result = await Minion(
        model="claude-sonnet-4-6",
        blueprint=coding_blueprint,
        environment="local",
    ).run("Add input validation for missing email in the signup endpoint")

    if isinstance(result, EscalationResult):
        print(f"Escalated at '{result.node}': {result.reason}")
        print(f"Branch: {result.branch}")
        return

    print(f"outcome : {result.outcome}")
    print(f"branch  : {result.branch}")
    print(f"pr      : {result.state.pr_url}")
    print(f"tokens  : {result.tokens}")
    print(f"duration: {result.duration_ms}ms")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
