"""Built-in search tools — find_files, search_files."""

from __future__ import annotations

from minion.core.context import RunContext
from minion.core.tool import tool


@tool(description="Find files by name or extension. Returns matching file paths. Use name_pattern for substring matching, use extension for filtering by file type (e.g. '.py', '.ts').")
async def find_files(
    ctx: RunContext,
    path: str = ".",
    name_pattern: str = "",
    extension: str = "",
    exclude_dirs: str = ".git,.venv,node_modules,__pycache__,.worktrees",
) -> str:
    """Find files by name pattern or extension.

    Uses `find` under the hood. name_pattern does substring matching on filenames.
    extension filters by file extension (include the dot, e.g. '.py').
    exclude_dirs is a comma-separated list of directory names to skip.
    """
    # Build find command
    cmd_parts = [f"find {path}"]

    # Add exclusions
    for d in exclude_dirs.split(","):
        d = d.strip()
        if d:
            cmd_parts.append(f"-not -path '*/{d}/*'")
            cmd_parts.append(f"-not -name '{d}'")

    # Add name pattern filter
    if name_pattern:
        cmd_parts.append(f"-name '*{name_pattern}*'")

    # Add extension filter — find uses -name for this
    if extension:
        cmd_parts.append(f"-name '*{extension}'")

    # Only files
    cmd_parts.append("-type f")
    cmd_parts.append("| sort")

    cmd = " ".join(cmd_parts)
    result = await ctx.exec(cmd)

    if not result.stdout.strip():
        return f"No files found matching criteria in {path}"

    lines = result.stdout.strip().splitlines()
    return f"Found {len(lines)} file(s):\n" + "\n".join(lines[:200])


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
    file_filter = f"--include='{file_pattern}'" if file_pattern else ""
    cmd = f"grep -r {flag_str} {file_filter} '{query}' {path} 2>/dev/null | head -n {max_results} || true"

    result = await ctx.exec(cmd)

    if not result.stdout.strip():
        return f"No files found containing '{query[:80]}' in {path}"

    lines = result.stdout.strip().splitlines()
    return f"Found {len(lines)} file(s) containing '{query[:80]}':\n" + "\n".join(lines[:max_results])
