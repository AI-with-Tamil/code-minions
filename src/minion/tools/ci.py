"""Built-in CI tools: run_tests, run_linter, get_test_output."""

from __future__ import annotations

from minion.core.context import RunContext
from minion.core.tool import tool


@tool(description="Run the project's test suite")
async def run_tests(ctx: RunContext, path: str = "tests/", flags: str = "-x --tb=short") -> str:
    result = await ctx.exec(f"pytest {path} {flags}")
    output = result.stdout
    if result.exit_code != 0:
        output += f"\n[tests failed with exit code {result.exit_code}]"
    return output


@tool(description="Run the linter with autofix")
async def run_linter(ctx: RunContext, command: str = "ruff check . --fix") -> str:
    result = await ctx.exec(command)
    output = result.stdout
    if result.exit_code != 0:
        output += f"\n[linter reported issues, exit code {result.exit_code}]"
    return output


@tool(description="Get the last test output from a previous run")
async def get_test_output(ctx: RunContext) -> str:
    # Return test output from state if available
    state = ctx.state
    if hasattr(state, "test_output"):
        return state.test_output
    return "(no test output recorded in state)"
