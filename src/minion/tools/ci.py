"""Built-in CI tools: run_tests, run_linter, get_test_output, summarize_failure_output."""

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


@tool(description="Summarize test or lint failure output into a concise, actionable report. Pass the raw failure text and get back file:line:error summaries.")
async def summarize_failure_output(ctx: RunContext, failure_text: str, max_items: int = 20) -> str:
    """Summarize test or lint failure output into a concise report.

    Extracts file:line:error patterns from failure text.
    Limits output to max_items to keep it focused for the agent.
    """
    if not failure_text.strip():
        return "(empty failure input)"

    lines = failure_text.strip().splitlines()

    # Collect error/FAIL lines (file:line patterns, assert failures, error: lines)
    errors = []
    for line in lines:
        stripped = line.strip()
        # Match specific error patterns: file paths with line numbers, test failures, exceptions
        is_error = any(pattern in stripped for pattern in [
            ".py:", "E ", "FAILED", "ERROR", "assert", "Error:", "error:",
            "SyntaxError", "TypeError", "ValueError", "ImportError",
        ])
        if is_error:
            # Skip noise lines
            if not any(skip in stripped for skip in [
                "=== test session starts ===",
                "=== short test summary info ===",
                "=== FAILURES ===",
                "collected",
                "passed",
                "warnings",
            ]):
                errors.append(stripped)

    if not errors:
        # Fall back to last 20 lines of the output
        errors = lines[-max_items:]
    else:
        errors = errors[:max_items]

    summary = [
        f"Failure summary ({len(errors)} items):",
        "---",
    ]
    for i, err in enumerate(errors, 1):
        summary.append(f"{i}. {err[:200]}")
    summary.append("---")
    summary.append(f"\nOriginal output: {len(lines)} lines total.")

    return "\n".join(summary)
