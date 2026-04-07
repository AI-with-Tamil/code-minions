# Task

The structured input to a Minion run. Not just a string.

## Interface

```python
from codeminions import Task

class Task:
    description: str                    # what to do (required)
    context: list[str] = []             # file paths, URLs, issue links
    acceptance: str = ""                # how we know it's done (e.g. "pytest passes")
    constraints: list[str] = []         # forbidden actions ("do not touch migrations")
    metadata: dict[str, Any] = {}       # arbitrary caller-supplied data (issue id, slack thread, etc.)
```

## Construction

```python
# Full
task = Task(
    description="Add rate limiting to /api/login",
    context=["src/api/login.py", "tests/test_login.py"],
    acceptance="pytest tests/test_login.py passes",
    constraints=["Do not modify the database schema"],
)

# String shorthand — always works
task = "Add rate limiting to /api/login"
# Minion internally converts: Task(description="Add rate limiting to /api/login")
```

## Availability in RunContext

```python
ctx.task.description    # str
ctx.task.context        # list[str]
ctx.task.acceptance     # str
ctx.task.constraints    # list[str]
ctx.task.metadata       # dict
```

## Behavior

- `Task` is immutable after construction — no node can modify the task
- String shorthand accepted everywhere a `Task` is accepted
- `ctx.task` is always a full `Task` object inside nodes (never a raw string)
