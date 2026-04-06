"""Built-in shell tools: run_command, git operations."""

from __future__ import annotations

from minion.core.context import RunContext
from minion.core.tool import tool


@tool(description="Run a shell command")
async def run_command(ctx: RunContext, command: str, cwd: str = "") -> str:
    result = await ctx.exec(command, cwd=cwd or None)
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR:\n{result.stderr}"
    if result.exit_code != 0:
        output += f"\n[exit code: {result.exit_code}]"
    return output


@tool(description="Show git diff of current changes")
async def git_diff(ctx: RunContext, staged: bool = False) -> str:
    flag = "--staged" if staged else ""
    result = await ctx.exec(f"git diff {flag}")
    return result.stdout


@tool(description="Show recent git log")
async def git_log(ctx: RunContext, n: int = 10) -> str:
    result = await ctx.exec(f"git log --oneline -n {n}")
    return result.stdout


@tool(description="Show git status")
async def git_status(ctx: RunContext) -> str:
    result = await ctx.exec("git status --short")
    return result.stdout


@tool(description="Stage files for commit")
async def git_add(ctx: RunContext, paths: str = "-A") -> str:
    result = await ctx.exec(f"git add {paths}")
    return result.stdout or "Files staged"


@tool(description="Create a git commit")
async def git_commit(ctx: RunContext, message: str) -> str:
    result = await ctx.exec(f'git commit -m "{message}"')
    return result.stdout
