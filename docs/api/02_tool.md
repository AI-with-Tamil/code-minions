# Tool

A typed, decorated Python function the LLM agent can call.

## Interface

```python
from minion import tool, RunContext

@tool(description: str = "", output_policy: ToolOutputPolicy = default_policy)
async def my_tool(ctx: RunContext, param: str, flag: bool = False) -> str:
    ...

# Sync also supported — auto-wrapped in executor
@tool(description="...")
def my_sync_tool(ctx: RunContext, param: str) -> str:
    ...
```

## Rules (enforced at import time, not runtime)

- First argument must be `ctx: RunContext` — no exceptions
- No `*args` or `**kwargs`
- All parameters must be explicitly typed
- Return type must be typed
- Violation raises `ToolDefinitionError` immediately on import

## Schema generation

Parameters after `ctx` become the JSON schema sent to the model:

```python
@tool(description="Search file contents")
async def grep(ctx: RunContext, pattern: str, path: str = ".", recursive: bool = True) -> list[str]:
    ...

# Generated schema:
{
  "name": "grep",
  "description": "Search file contents",
  "input_schema": {
    "type": "object",
    "properties": {
      "pattern":   {"type": "string"},
      "path":      {"type": "string", "default": "."},
      "recursive": {"type": "boolean", "default": true}
    },
    "required": ["pattern"]
  }
}
```

## Execution contract

- Tool errors are caught and returned as structured `ToolResult(error=...)` — never raised to Blueprint
- Output exceeding `output_policy.max_chars` is truncated with a note
- All tool calls recorded in `ctx.trace` automatically by the runner (not by the tool)
- `ctx` is injected by the runner — tools never construct their own context

## ToolOutputPolicy

```python
class ToolOutputPolicy:
    max_chars: int = 50_000
    truncation_msg: str = "... [truncated, {remaining} chars omitted]"

# Per-tool override
@tool(description="Read a file", output_policy=ToolOutputPolicy(max_chars=10_000))
async def read_file(ctx: RunContext, path: str) -> str: ...
```

## ToolResult (internal — what the runner returns to the model)

```python
class ToolResult:
    id: str
    content: str | None
    error: str | None
    recoverable: bool = True   # False = escalate immediately
```

## Built-in tool subsets

```python
from minion.tools import CODE_TOOLS, SHELL_TOOLS, CI_TOOLS, WEB_TOOLS, PROGRESS_TOOLS

CODE_TOOLS      # read_file, write_file, edit_file, grep, glob, list_dir
SHELL_TOOLS     # run_command, git_diff, git_log, git_status, git_add, git_commit, diff_history
CI_TOOLS        # run_tests, run_linter, get_test_output
WEB_TOOLS       # web_fetch, web_search
PROGRESS_TOOLS  # write_todos, get_todos
```

### CODE_TOOLS

| Tool | Description |
|------|-------------|
| `read_file` | Read file contents |
| `write_file` | Write content to a file (creates or overwrites) |
| `edit_file` | Exact string replacement in a file |
| `grep` | Regex content search across files |
| `glob` | Find files matching a glob pattern |
| `list_dir` | List files and directories (depth-limited, hides dotfiles) |

### SHELL_TOOLS

| Tool | Description |
|------|-------------|
| `run_command` | Run a shell command |
| `git_diff` | Show git diff (staged or unstaged) |
| `git_log` | Show recent git log |
| `git_status` | Show git status (short format) |
| `git_add` | Stage files for commit |
| `git_commit` | Create a git commit |
| `diff_history` | Show all changes made during this session (files + stats) |

### CI_TOOLS

| Tool | Description |
|------|-------------|
| `run_tests` | Run pytest with configurable path and flags |
| `run_linter` | Run linter with autofix (default: ruff) |
| `get_test_output` | Get last test output from state |

### WEB_TOOLS

| Tool | Description |
|------|-------------|
| `web_fetch` | Fetch a URL via curl, strip HTML tags, return text content |
| `web_search` | Search the web (uses ddgr/googler CLI, or DuckDuckGo lite fallback) |

For production web search, prefer an MCP search server (Brave, Google) for structured results.

### PROGRESS_TOOLS

| Tool | Description |
|------|-------------|
| `write_todos` | Create/update a structured task list for tracking multi-step work |
| `get_todos` | Get the current task list with status indicators |

## MCP tools

```python
from minion.tools import (
    MCPClient,
    MCPServerConfig,
    complete_mcp_prompt,
    complete_mcp_resource_template,
    get_mcp_prompt,
    get_mcp_display_name,
    list_mcp_prompts,
    list_mcp_resource_templates,
    list_mcp_resources,
    mcp_tools,
    read_mcp_resource,
    register_mcp_server,
    subscribe_mcp_resource,
    unsubscribe_mcp_resource,
)

mcp_tools(server: str, tools: list[str] | None = None) -> list[Tool]
# tools=None loads all tools from that server
# tools=[...] loads only named tools (curated subset)

register_mcp_server(
    "github",
    MCPServerConfig(
        transport="streamable_http",
        url="https://mcp.example.com/github/mcp",
        headers={"Authorization": "Bearer ..."},
    ),
)

tools = mcp_tools("github", tools=["create_pr", "get_issue"])

resources = list_mcp_resources("github")
readme = read_mcp_resource("github", "repo://README.md")
templates = list_mcp_resource_templates("github")

prompts = list_mcp_prompts("github")
review = get_mcp_prompt("github", "review_pr", {"pr_number": "123"})

styles = complete_mcp_prompt(
    "github",
    name="review_pr",
    argument_name="style",
    argument_value="f",
)

repos = complete_mcp_resource_template(
    "github",
    uri_template="repo://{owner}/{repo}",
    argument_name="repo",
    argument_value="min",
    context_arguments={"owner": "tamilarasan"},
)
```

Supported transports:
- `stdio` — primary local/server subprocess mode
- `streamable_http` — latest standard remote transport
- `sse` — legacy compatibility for older MCP servers

Advanced path:
- `MCPClient` for direct access to `list_tools`, `call_tool`, `list_resources`, `read_resource`, `list_prompts`, and `get_prompt`
- `MCPClient` also exposes `list_resource_templates`, `complete_prompt`, `complete_resource_template`, `subscribe_resource`, `unsubscribe_resource`, and `send_ping`
- session initialization captures server capabilities and protocol metadata
- `get_mcp_display_name()` uses MCP metadata precedence for user-facing labels

Named server resolution order:
- explicit keyword overrides passed to `mcp_tools(...)`
- `register_mcp_server(...)`
- environment variables like `MINION_MCP_GITHUB_COMMAND` or `MINION_MCP_GITHUB_URL`
