# Minion

The runner. Ties model, blueprint, and environment together. The entry point users interact with.

## Interface

```python
from minion import Minion

Minion(
    model:          str | BaseModelProtocol = "claude-sonnet-4-6",
    blueprint:      str | Blueprint = "coding",
    environment:    str | BaseEnvironment = "local",
    config:         RunConfig | None = None,
    storage:        str | None = None,       # SQLite path, e.g. "./runs.db"
    max_concurrent: int = 1,
)
```

## Run methods

```python
# Async — primary
result: RunResult = await minion.run(task: str | Task)

# Sync convenience
result: RunResult = minion.run_sync(task: str | Task)

# Streaming — yields events as they happen
async for event in minion.run_stream(task: str | Task):
    print(event)

# Batch — runs tasks in parallel up to max_concurrent
results: list[RunResult] = await minion.run_batch(tasks: list[str | Task])
```

## Event hooks

```python
from minion import MinionEvent

@minion.on(MinionEvent.NODE_START)
async def on_node_start(event: NodeStartEvent) -> None:
    print(f"Starting node: {event.node}")

@minion.on(MinionEvent.TOOL_CALL)
async def on_tool_call(event: ToolCallEvent) -> None:
    print(f"Tool called: {event.tool} args={event.args}")

@minion.on(MinionEvent.NODE_COMPLETE)
async def on_node_complete(event: NodeCompleteEvent) -> None:
    print(f"Node done: {event.node} duration={event.duration_ms}ms")
```

## Zero-config

```python
# Works out of the box
result = await Minion().run("Fix the null check in auth.py")

# Resolution order:
# 1. Constructor args
# 2. minion.toml
# 3. pyproject.toml [tool.minion]
# 4. Environment variables (MINION_MODEL, MINION_BLUEPRINT, etc.)
# 5. SDK defaults: claude-sonnet-4-6, coding blueprint, LocalEnv(".")
```

## Configuration file

```toml
# minion.toml or pyproject.toml [tool.minion]
[minion]
model       = "claude-sonnet-4-6"
blueprint   = "coding"
environment = "docker"

[minion.docker]
image   = "python:3.12"
network = "none"

[minion.feedback]
lint_command = "ruff check . --fix"
test_command = "pytest tests/ -x"
```

## MinionEvent

```python
class MinionEvent(str, Enum):
    RUN_START      = "run_start"
    RUN_COMPLETE   = "run_complete"
    NODE_START     = "node_start"
    NODE_COMPLETE  = "node_complete"
    NODE_SKIP      = "node_skip"
    TOOL_CALL      = "tool_call"
    TOOL_RESULT    = "tool_result"
    AGENT_DONE     = "agent_done"
    ESCALATION     = "escalation"
```
