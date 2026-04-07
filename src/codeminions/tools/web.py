"""Built-in web tools: web_fetch, web_search."""

from __future__ import annotations

import html
import re
import shlex
from urllib.parse import quote as urlquote

from codeminions.core.context import RunContext
from codeminions.core.tool import tool


def _strip_html(raw: str, max_chars: int = 30_000) -> str:
    """Strip HTML tags and collapse whitespace. Keep it simple — no deps."""
    # Remove script/style blocks
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", text)
    # Decode entities
    text = html.unescape(text)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


@tool(description="Fetch a URL and return its text content")
async def web_fetch(ctx: RunContext, url: str, max_chars: int = 30_000) -> str:
    """Fetch a URL via curl and return stripped text content.

    Works in any environment that has curl (Docker, local, worktree).
    No Python HTTP dependency required.
    """
    result = await ctx.exec(
        f"curl -sL --max-time 15 --max-filesize 2097152 "
        f"-H 'User-Agent: Minion-SDK/0.1' "
        f"{shlex.quote(url)}"
    )
    if result.exit_code != 0:
        return f"[fetch failed: {result.stderr.strip() or 'exit code ' + str(result.exit_code)}]"

    content = result.stdout
    # If it looks like HTML, strip tags
    if "<html" in content[:500].lower() or "<body" in content[:1000].lower():
        content = _strip_html(content, max_chars)
    return content[:max_chars]


@tool(description="Search the web and return results")
async def web_search(ctx: RunContext, query: str, num_results: int = 5) -> str:
    """Search the web using a configurable backend.

    Tries these backends in order:
    1. ddgr (DuckDuckGo CLI) if installed
    2. Falls back to a message suggesting MCP search servers

    For production use, prefer an MCP search server (Google, Brave, etc.)
    which gives structured results and higher quality.
    """
    # Try ddgr (DuckDuckGo CLI)
    check = await ctx.exec("command -v ddgr")
    if check.exit_code == 0:
        result = await ctx.exec(
            f"ddgr --json -n {num_results} {shlex.quote(query)} 2>/dev/null"
        )
        if result.exit_code == 0 and result.stdout.strip():
            return result.stdout

    # Try googler
    check = await ctx.exec("command -v googler")
    if check.exit_code == 0:
        result = await ctx.exec(
            f"googler --json -n {num_results} {shlex.quote(query)} 2>/dev/null"
        )
        if result.exit_code == 0 and result.stdout.strip():
            return result.stdout

    # Fallback: curl-based DuckDuckGo lite
    result = await ctx.exec(
        f"curl -sL --max-time 10 "
        f"'https://lite.duckduckgo.com/lite/?q={urlquote(query)}' "
        f"-H 'User-Agent: Minion-SDK/0.1'"
    )
    if result.exit_code == 0 and result.stdout.strip():
        text = _strip_html(result.stdout, 8000)
        if len(text) > 50:
            return text

    return (
        "[web_search unavailable — no search CLI found]\n"
        "Install ddgr (brew install ddgr) for built-in search,\n"
        "or use an MCP search server for production:\n"
        "  mcp_tools('brave-search', tools=['search'])\n"
        "  mcp_tools('google-search', tools=['search'])"
    )
