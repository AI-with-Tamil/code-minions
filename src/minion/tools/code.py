"""Built-in code tools: read_file, write_file, edit_file, grep, glob."""

from __future__ import annotations

import re
import shlex

from minion.core.context import RunContext
from minion.core.tool import tool


@tool(description="Read the contents of a file")
async def read_file(ctx: RunContext, path: str) -> str:
    return await ctx.read(path)


@tool(description="Write content to a file (creates or overwrites)")
async def write_file(ctx: RunContext, path: str, content: str) -> str:
    await ctx.write(path, content)
    return f"Wrote {len(content)} chars to {path}"


@tool(description="Edit a file by replacing the first occurrence of old text with new text. Use this for surgical edits. The old text must exist exactly as written.")
async def edit_file(ctx: RunContext, path: str, old: str, new: str) -> str:
    """Edit a file by replacing old text with new text.

    Validates preconditions: old text must be found in the file.
    Returns clear error messages when the old text is not found,
    so the agent can self-correct without wasting a round.
    """
    # Read current content to validate before editing
    try:
        content = await ctx.read(path)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {path}") from None

    if old not in content:
        # Provide helpful context so the agent can fix its call
        # Find similar lines if old contains newlines
        lines = old.strip().splitlines()
        if len(lines) == 1:
            # Single line: check if a close match exists
            content_lines = content.splitlines()
            similar = [
                (i, line) for i, line in enumerate(content_lines)
                if old.strip()[:40] in line or line[:40] in old.strip()
            ]
            hint = ""
            if similar:
                lineno, match = similar[0]
                hint = f"\nDid you mean line {lineno + 1}: {match[:120]}?"
            raise ValueError(
                f"Text not found in {path}: {old[:100]}...{hint}\n"
                "Hint: read the file first and use the exact text to replace."
            )
        else:
            # Multi-line block: show available content around the first line
            first_line = lines[0].strip()
            hint = ""
            if first_line and first_line not in content:
                content_lines = content.splitlines()
                similar = [
                    (i, line) for i, line in enumerate(content_lines)
                    if first_line[:30] in line
                ]
                if similar:
                    lineno, match = similar[0]
                    hint = f"\nFirst line not found. Did you mean line {lineno + 1}: {match[:120]}?"
            raise ValueError(
                f"Multi-line text not found in {path}.\n"
                f"First line: {first_line[:80]}{hint}\n"
                "Hint: read the file first and use the exact block to replace."
            )

    await ctx.env.edit(path, old, new)
    new_len = len(new)
    old_len = len(old)
    delta = new_len - old_len
    return f"Edited {path} ({'+' if delta >= 0 else ''}{delta} chars)"


@tool(description="Append content to the end of a file. Creates the file if it doesn't exist.")
async def append_file(ctx: RunContext, path: str, content: str) -> str:
    """Append content to the end of a file.

    If the file doesn't exist, creates it. Always appends — never overwrites.
    """
    try:
        existing = await ctx.read(path)
        combined = existing + content
        await ctx.write(path, combined)
        return f"Appended {len(content)} chars to {path}"
    except FileNotFoundError:
        await ctx.write(path, content)
        return f"Created and wrote {len(content)} chars to {path}"


@tool(description="Insert content before the first line that matches a given pattern (exact substring match).")
async def insert_before(ctx: RunContext, path: str, target: str, content: str) -> str:
    """Insert content before a target line in a file.

    The target is matched as an exact substring against each line.
    The first matching line wins. Fails clearly if the target is not found.
    """
    try:
        text = await ctx.read(path)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {path}") from None

    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if target in line:
            # Ensure content ends with newline before insertion
            insert = content if content.endswith("\n") else content + "\n"
            lines.insert(i, insert)
            new_text = "".join(lines)
            await ctx.write(path, new_text)
            return f"Inserted {len(content)} chars before line {i + 1} in {path}"

    # Target not found — give actionable error
    raise ValueError(
        f"Target text not found in {path}: {target[:100]}\n"
        "Hint: read the file first and verify the target line exists."
    )


@tool(description="Insert content after the first line that matches a given pattern (exact substring match).")
async def insert_after(ctx: RunContext, path: str, target: str, content: str) -> str:
    """Insert content after a target line in a file.

    The target is matched as an exact substring against each line.
    The first matching line wins. Fails clearly if the target is not found.
    """
    try:
        text = await ctx.read(path)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {path}") from None

    lines = text.splitlines(keepends=True)
    for i, line in enumerate(lines):
        if target in line:
            # Ensure content ends with newline before insertion
            insert = content if content.endswith("\n") else content + "\n"
            lines.insert(i + 1, insert)
            new_text = "".join(lines)
            await ctx.write(path, new_text)
            return f"Inserted {len(content)} chars after line {i + 1} in {path}"

    # Target not found — give actionable error
    raise ValueError(
        f"Target text not found in {path}: {target[:100]}\n"
        "Hint: read the file first and verify the target line exists."
    )


@tool(description="Replace text in a file using a regex pattern. The pattern is a Python regex string. Only replaces the first match unless replace_all=True.")
async def replace_regex(ctx: RunContext, path: str, pattern: str, replacement: str, replace_all: bool = False) -> str:
    """Replace text in a file using a regex pattern.

    Uses Python re.sub under the hood. Be careful with regex special characters.
    """
    try:
        text = await ctx.read(path)
    except FileNotFoundError:
        raise FileNotFoundError(f"File not found: {path}") from None

    try:
        if replace_all:
            new_text, count = re.subn(pattern, replacement, text)
        else:
            new_text, count = re.subn(pattern, replacement, text, count=1)
    except re.error as e:
        raise ValueError(f"Invalid regex pattern: {e}") from e

    if count == 0:
        raise ValueError(
            f"Pattern '{pattern}' matched 0 occurrences in {path}.\n"
            "Hint: read the file first and verify the pattern matches."
        )

    await ctx.write(path, new_text)
    return f"Replaced {count} occurrence(s) of '{pattern}' in {path}"


@tool(description="Check if a file or directory exists. Returns 'true' or 'false'.")
async def file_exists(ctx: RunContext, path: str) -> str:
    """Check whether a file or directory exists. Returns 'true' or 'false'."""
    exists = await ctx.env.exists(path)
    return "true" if exists else "false"


@tool(description="Search file contents with a regex pattern")
async def grep(ctx: RunContext, pattern: str, path: str = ".", recursive: bool = True) -> str:
    flag = "-r" if recursive else ""
    cmd = f"grep -n {flag} {shlex.quote(pattern)} {shlex.quote(path)} 2>/dev/null || true".strip()
    result = await ctx.exec(cmd)
    return result.stdout


@tool(description="Find files matching a glob pattern")
async def glob(ctx: RunContext, pattern: str) -> list[str]:
    return await ctx.env.glob(pattern)


@tool(description="List files and directories in a path")
async def list_dir(ctx: RunContext, path: str = ".", max_depth: int = 1) -> str:
    """List directory contents. Returns file/dir names with type indicators.

    Agents use this to orient in unfamiliar codebases before reading files.
    """
    if max_depth < 1:
        max_depth = 1
    if max_depth > 3:
        max_depth = 3
    # Use find for depth-limited listing with type indicators
    result = await ctx.exec(
        f"find {shlex.quote(path)} -maxdepth {max_depth} -not -path '*/\\.*' "
        f"| sort"
    )
    return result.stdout
