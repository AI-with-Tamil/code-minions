# Nodes

A node is one step in a Blueprint. Each node has a name, an optional condition, and failure policy.

---

## DeterministicNode

Pure Python. No LLM. Always runs the same way.

```python
from minion import DeterministicNode

DeterministicNode(
    name:       str,
    fn:         Callable[[RunContext], Awaitable[None] | None],
    condition:  Callable[[RunContext], bool] | None = None,
    on_failure: Literal["abort", "continue", "escalate"] = "escalate",
)
```

### Examples

```python
DeterministicNode("create_branch", fn=create_branch)
DeterministicNode("lint",          fn=run_lint)
DeterministicNode("push",          fn=push_branch, on_failure="abort")
```

### Behavior

- `fn` receives `ctx: RunContext`, mutates `ctx.state`, returns `None`
- Exception from `fn` → `on_failure` policy applied
- No token cost, no LLM call, no tool calls

---

## AgentNode

LLM loop with tool calling. Runs until `done()` is called or budget exhausted.

```python
from minion import AgentNode

AgentNode(
    name:            str,
    system_prompt:   str,
    tools:           list[Tool],
    condition:       Callable[[RunContext], bool] | None = None,
    max_iterations:  int = 80,            # max LLM round-trips per execution
    token_budget:    int = 50_000,        # input+output token cap for this node
    max_rounds:      int = 1,             # max times Blueprint can re-enter this node
    on_max_rounds:   Literal["escalate", "abort", "continue"] = "escalate",
    on_failure:      Literal["abort", "continue", "escalate"] = "escalate",
)
```

### max_iterations vs max_rounds

- `max_iterations` — LLM round-trips within a **single** execution of the node
- `max_rounds` — how many times the **Blueprint** can re-enter this node across the run
- Example: `max_iterations=40, max_rounds=2` means up to 40 LLM calls each time, re-enterable twice

### done() tool

Every `AgentNode` automatically receives a `done` tool. Agent must call it to complete.

```python
# Auto-injected — agent calls this when finished
done(
    summary:       str,           # what was done
    files_changed: list[str] = [], # files modified
)
# Raises _AgentDone internally — caught by runner, not an error
```

If budget exhausted without `done()` call → treated as node failure → `on_failure` policy applied.

### Behavior

- Tools in `tools` list are the only tools available to this node
- `system_prompt` is rendered at runtime against the current `ctx`
- Prompt templates may reference task and state values such as `{task.description}` or `{state.branch}`
- State from prior nodes available via `ctx.state` (read-only recommended, but writable)
- Messages pruned between nodes (context does not bleed across nodes by default)

---

## JudgeNode

A second LLM that evaluates the output of a prior AgentNode.
Vetoes bad output and re-enters the target node.

```python
from minion import JudgeNode

JudgeNode(
    name:       str,
    evaluates:  str,                                           # name of AgentNode to evaluate
    criteria:   str,                                           # what good output looks like
    on_veto:    Literal["retry", "escalate", "continue"] = "retry",
    max_vetoes: int = 2,
)
```

### Example

```python
JudgeNode(
    name="review",
    evaluates="implement",
    criteria=(
        "The change matches the task description. "
        "No unrelated files changed. "
        "No scope creep. "
        "No commented-out code."
    ),
    on_veto="retry",
    max_vetoes=2,
)
```

### Behavior

- Runs after the `evaluates` node completes
- Judge receives: task description, git diff, agent summary from `done()`
- Judge returns: `approve` or `veto(reason: str)`
- On veto + `on_veto="retry"`: re-enters the target AgentNode with the veto reason appended to system prompt
- `max_vetoes` exhausted → applies `on_veto` policy (if "retry", escalates instead)
- Spotify data: 25% veto rate, 50% self-correction rate after veto

---

## ParallelNode

Runs multiple child nodes concurrently. Merges state on completion.

```python
from minion import ParallelNode

ParallelNode(
    name:       str,
    nodes:      list[DeterministicNode | AgentNode | JudgeNode],
    on_failure: Literal["abort", "continue", "escalate"] = "escalate",
)
```

### Example

```python
ParallelNode(
    "gather_context",
    nodes=[
        DeterministicNode("fetch_issue",    fn=fetch_issue),
        DeterministicNode("search_api",     fn=search_api_files),
        DeterministicNode("search_tests",   fn=search_test_files),
    ],
)
```

### Behavior

- Child nodes run concurrently via `asyncio.gather`
- Each child node receives the same `ctx` — state mutations are applied in completion order
- If any child fails: `on_failure` policy applied to the `ParallelNode` as a whole
- `AgentNode` children allowed but sequential ordering of state writes not guaranteed — use with care

---

## LoopNode

Iterates a reusable sub-blueprint over a discovered list of targets.
Use this for migration and codemod workflows where each item follows the same bounded process.

```python
from minion import LoopNode

LoopNode(
    name:           str,
    sub_blueprint:  Blueprint,
    iterate_over:   Callable[[RunContext], list[Any]],
    bind:           Callable[[RunContext, Any], None],
    max_iterations: int | None = None,
    on_failure:     Literal["abort", "continue", "escalate"] = "continue",
)
```

### Example

```python
LoopNode(
    "migrate_all",
    sub_blueprint=per_file_blueprint,
    iterate_over=lambda ctx: ctx.state.targets,
    bind=lambda ctx, target: setattr(ctx.state, "current_target", target),
    on_failure="continue",
)
```

### Behavior

- `iterate_over(ctx)` returns the ordered list of items to process
- `bind(ctx, item)` injects per-item state before running the sub-blueprint
- The same parent `ctx.state` is reused across iterations
- Each iteration runs the same `sub_blueprint`
- Iteration-level failures obey `on_failure`
- `max_iterations` is a hard cap on processed items to avoid unbounded loops
- This is a workflow primitive, not a general-purpose looping language

---

## Condition

All nodes accept `condition=`:

```python
# Lambda (inline)
condition=lambda ctx: ctx.state.lint_failed

# Named predicate — reusable
def lint_failed(ctx: RunContext) -> bool:
    return ctx.state.lint_failed

AgentNode("fix_lint", condition=lint_failed, ...)
```

### Behavior

- `condition` evaluated before node executes
- `False` → node skipped, `node_skipped` event recorded in trace
- `None` → node always runs
