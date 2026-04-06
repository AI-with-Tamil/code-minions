"""Built-in code tools: read_file, write_file, edit_file, grep, glob."""

from __future__ import annotations

from minion.core.context import RunContext
from minion.core.tool import tool


@tool(description="Read the contents of a file")
async def read_file(ctx: RunContext, path: str) -> str:
    return await ctx.read(path)


@tool(description="Write content to a file (creates or overwrites)")
async def write_file(ctx: RunContext, path: str, content: str) -> str:
    await ctx.write(path, content)
    return f"Wrote {len(content)} chars to {path}"


@tool(description="Edit a file by replacing old text with new text")
async def edit_file(ctx: RunContext, path: str, old: str, new: str) -> str:
    await ctx.env.edit(path, old, new)
    return f"Edited {path}"


@tool(description="Search file contents with a regex pattern")
async def grep(ctx: RunContext, pattern: str, path: str = ".", recursive: bool = True) -> str:
    flag = "-r" if recursive else ""
    result = await ctx.exec(f"grep -n {flag} '{pattern}' {path} 2>/dev/null || true")
    return result.stdout


@tool(description="Find files matching a glob pattern")
async def glob(ctx: RunContext, pattern: str) -> list[str]:
    return await ctx.env.glob(pattern)
