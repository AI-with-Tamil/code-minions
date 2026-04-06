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
from minion.tools import CODE_TOOLS, SHELL_TOOLS, CI_TOOLS

CODE_TOOLS   # read_file, write_file, edit_file, grep, glob
SHELL_TOOLS  # run_command, git_diff, git_log, git_status, git_add, git_commit
CI_TOOLS     # run_tests, run_linter, get_test_output
```

## MCP tools

```python
from minion.tools import mcp_tools

mcp_tools(server: str, tools: list[str] | None = None) -> list[Tool]
# tools=None loads all tools from that server
# tools=[...] loads only named tools (curated subset)
```
