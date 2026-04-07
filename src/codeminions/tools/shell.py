"""Built-in shell tools: run_command, git operations."""

from __future__ import annotations

import shlex

from codeminions.core.context import RunContext
from codeminions.core.tool import tool


@tool(description="Run a shell command")
async def run_command(ctx: RunContext, command: str, cwd: str = "") -> str:
    result = await ctx.exec(command, cwd=cwd or None)
    output = result.stdout
    if result.stderr:
        output += f"\nSTDERR:\n{result.stderr}"
    if result.exit_code != 0:
        output += f"\n[exit code: {result.exit_code}]"
    return output


@tool(description="Print the current working directory")
async def pwd(ctx: RunContext) -> str:
    result = await ctx.exec("pwd")
    return result.stdout.strip()


@tool(description="Show the contents of a specific git commit")
async def git_show(ctx: RunContext, ref: str = "HEAD") -> str:
    result = await ctx.exec(f"git show --stat {shlex.quote(ref)}")
    return result.stdout


@tool(description="Switch to a different git branch")
async def git_checkout(ctx: RunContext, branch: str) -> str:
    result = await ctx.exec(f"git checkout {shlex.quote(branch)}")
    output = result.stdout
    if result.stderr:
        output += f"\n{result.stderr}"
    if result.exit_code != 0:
        output += f"\n[exit code: {result.exit_code}]"
    return output


@tool(description="Create a new git branch")
async def git_create_branch(ctx: RunContext, branch: str, start_point: str = "") -> str:
    cmd = f"git checkout -b {shlex.quote(branch)}"
    if start_point:
        cmd += f" {shlex.quote(start_point)}"
    result = await ctx.exec(cmd)
    output = result.stdout
    if result.stderr:
        output += f"\n{result.stderr}"
    if result.exit_code != 0:
        output += f"\n[exit code: {result.exit_code}]"
    return output


@tool(description="Push the current branch to the remote")
async def git_push(ctx: RunContext, remote: str = "origin", set_upstream: bool = True, branch: str = "") -> str:
    flag = "-u" if set_upstream else ""
    parts = ["git", "push"]
    if flag:
        parts.append(flag)
    parts.append(shlex.quote(remote))
    if branch:
        parts.append(shlex.quote(branch))
    result = await ctx.exec(" ".join(parts))
    output = result.stdout
    if result.stderr:
        output += f"\n{result.stderr}"
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
    if paths.strip() == "-A":
        cmd = "git add -A"
    else:
        try:
            parsed_paths = shlex.split(paths)
        except ValueError as e:
            raise ValueError(f"Invalid git add paths: {e}") from e
        if not parsed_paths:
            raise ValueError("git_add requires at least one path or '-A'")
        cmd = "git add " + " ".join(shlex.quote(path) for path in parsed_paths)
    result = await ctx.exec(cmd)
    return result.stdout or "Files staged"


@tool(description="Create a git commit")
async def git_commit(ctx: RunContext, message: str) -> str:
    result = await ctx.exec(f"git commit -m {shlex.quote(message)}")
    return result.stdout


@tool(description="Show what files changed and a summary of diffs")
async def diff_history(ctx: RunContext, stat_only: bool = True) -> str:
    """Show changes made during this session.

    Checks both staged and unstaged changes. Gives the agent awareness of
    what it has modified so far without needing to manually run git diff.
    """
    parts = []

    # Changed files summary
    status = await ctx.exec("git status --short")
    if status.stdout.strip():
        parts.append("Changed files:\n" + status.stdout.strip())

    if stat_only:
        # Compact summary: file names + lines changed
        stat = await ctx.exec("git diff --stat HEAD 2>/dev/null || git diff --stat")
        if stat.stdout.strip():
            parts.append("\nDiff stats:\n" + stat.stdout.strip())
    else:
        # Full diff
        diff = await ctx.exec("git diff HEAD 2>/dev/null || git diff")
        if diff.stdout.strip():
            parts.append("\nFull diff:\n" + diff.stdout.strip())

    if not parts:
        return "(no changes detected)"
    return "\n".join(parts)
