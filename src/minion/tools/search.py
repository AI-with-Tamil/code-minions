"""Built-in search tools — find_files, search_files."""

from __future__ import annotations

from pathlib import PurePath
import shlex

from minion.core.context import RunContext
from minion.core.tool import tool


@tool(description="Find files by name and/or extension. Returns matching file paths. Use name_pattern for substring matching, extension for file-type filtering (e.g. '.py', '.ts'). If both are provided, files matching either condition are returned.")
async def find_files(
    ctx: RunContext,
    path: str = ".",
    name_pattern: str = "",
    extension: str = "",
    exclude_dirs: str = ".git,.venv,node_modules,__pycache__,.worktrees",
) -> str:
    """Find files by name pattern and/or extension.

    Uses `find` under the hood. name_pattern does substring matching on filenames.
    extension filters by file extension (include the dot, e.g. '.py').
    exclude_dirs is a comma-separated list of directory names to skip.
    """
    # Build find command
    cmd_parts = [f"find {shlex.quote(path)}"]

    # Add exclusions
    for d in exclude_dirs.split(","):
        d = d.strip()
        if d:
            cmd_parts.append(f"-not -path {shlex.quote(f'*/{d}/*')}")
            cmd_parts.append(f"-not -name {shlex.quote(d)}")

    # Only files
    cmd_parts.append("-type f")
    cmd_parts.append("| sort")

    cmd = " ".join(cmd_parts)
    result = await ctx.exec(cmd)

    matches = [line for line in result.stdout.strip().splitlines() if line.strip()]
    if name_pattern or extension:
        filtered: list[str] = []
        for entry in matches:
            filename = PurePath(entry).name
            name_ok = name_pattern in filename if name_pattern else False
            ext_ok = filename.endswith(extension) if extension else False
            if name_pattern and extension:
                if name_ok or ext_ok:
                    filtered.append(entry)
            elif name_pattern and name_ok:
                filtered.append(entry)
            elif extension and ext_ok:
                filtered.append(entry)
        matches = filtered

    if not matches:
        return f"No files found matching criteria in {path}"

    return f"Found {len(matches)} file(s):\n" + "\n".join(matches[:200])


@tool(description="Search for files containing specific text content. Like grep but optimized for finding which files match, not showing the full content. Returns file paths only.")
async def search_files(
    ctx: RunContext,
    query: str,
    path: str = ".",
    case_sensitive: bool = False,
    file_pattern: str = "",
    max_results: int = 50,
) -> str:
    """Search for files containing specific text content.

    Returns only file paths (not the matched content). Use grep to see
    the actual matching lines. This tool is for discovering which files
    are relevant to a topic.

    Args:
        query: Text to search for.
        path: Root directory to search from.
        case_sensitive: Whether to match case-sensitively.
        file_pattern: Glob pattern to filter files (e.g. '*.py').
        max_results: Maximum number of files to return.
    """
    # Use grep -l for file-only output
    if case_sensitive:
        flag_str = "-l"
    else:
        flag_str = "-li"
    file_filter = f"--include={shlex.quote(file_pattern)} " if file_pattern else ""
    max_results = max(1, min(max_results, 200))
    cmd = (
        f"grep -r {flag_str} {file_filter}{shlex.quote(query)} {shlex.quote(path)} "
        f"2>/dev/null | head -n {max_results} || true"
    )

    result = await ctx.exec(cmd)

    if not result.stdout.strip():
        return f"No files found containing '{query[:80]}' in {path}"

    lines = result.stdout.strip().splitlines()
    return f"Found {len(lines)} file(s) containing '{query[:80]}':\n" + "\n".join(lines[:max_results])
