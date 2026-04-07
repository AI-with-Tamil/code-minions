# RunResult / EscalationResult

The output of a Minion run.

## RunResult

```python
from codeminions import RunResult

@dataclass
class RunResult:
    run_id:      str
    outcome:     Literal["passed", "failed", "escalated"]
    branch:      str | None
    diff:        str                # git diff of all changes
    summary:     str                # from agent's done() call
    state:       BaseModel          # full typed state at end of run
    trace:       Trace              # full execution trace
    tokens:      int                # total tokens used
    duration_ms: int
```

## EscalationResult

Returned when a node exceeds `max_rounds` with `on_max_rounds="escalate"`,
or when a node fails with `on_failure="escalate"`.

```python
from codeminions import EscalationResult

@dataclass
class EscalationResult(RunResult):
    node:         str    # which node triggered escalation
    reason:       str    # why (budget, failure, judge veto)
    last_failure: str    # last error/failure output
```

`EscalationResult.outcome` is always `"escalated"`.

## Checking outcome

```python
result = await Minion().run(task)

# Pattern 1 — isinstance check
if isinstance(result, EscalationResult):
    print(f"Escalated at '{result.node}': {result.reason}")
else:
    print(f"Passed. Branch: {result.branch}")

# Pattern 2 — outcome string
if result.outcome == "passed":
    result.open_pr()
```

## Actions

```python
result.open_pr()     # creates PR via gh cli, returns PR URL
result.push()        # pushes branch if not already pushed
result.inspect()     # opens trace viewer in terminal
```

## Test assertions

```python
result.assert_passed()
result.assert_failed()
result.assert_escalated()
result.assert_outcome(outcome: Literal["passed", "failed", "escalated"])

result.assert_node_ran(name: str)
result.assert_node_skipped(name: str)
result.assert_nodes_ran_in_order(*names: str)

result.assert_tool_called(name: str, **kwargs)       # kwargs match tool args
result.assert_tool_not_called(name: str)

result.assert_tokens_under(limit: int)
result.assert_duration_under(ms: int)
```

## Judge assertions

For blueprints that include `JudgeNode`:

```python
result.assert_judge_approved(node: str)        # JudgeNode produced APPROVE
result.assert_judge_vetoed(node: str, reason: str | None = None)  # at least one VETO
verdicts = result.judge_verdicts()             # {node_name: "approved" | "vetoed: <reason>"}
```

`judge_verdicts()` returns the **last** verdict per judge node — if a node vetoed then retried to approval, it returns `"approved"`.

```python
result = await Minion(blueprint=spotify_blueprint).run(task)
result.assert_judge_approved("judge")
verdicts = result.judge_verdicts()
# {"judge": "approved"}
```

## Trace

```python
@dataclass
class Trace:
    run_id: str
    events: list[TraceEvent]        # append-only

class TraceEvent(TypedDict):
    type:      str                  # node_start | node_complete | node_skip | tool_call | tool_result | ...
    node:      str
    timestamp: float
    data:      dict                 # event-specific payload
```

### Event types

| Type | When | Key data fields |
|------|------|-----------------|
| `node_start` | node begins | — |
| `node_complete` | node finishes | `error` (if failed) |
| `node_skip` | condition returned False | — |
| `tool_call` | agent invokes a tool | `tool`, `args` |
| `tool_result` | tool returns | `tool`, `result`, `error` |
| `agent_done` | agent calls `done()` | `summary`, `files_changed` |
| `judge_approve` | judge APPROVE | — |
| `judge_veto` | judge VETO | `reason`, `veto_number` |
| `agent_max_rounds` | rounds budget hit | `max_rounds`, `on_max_rounds` |
| `log` | `ctx.log()` call | `message` |

### Trace query helpers

```python
trace = result.trace

# Filter by event type
starts = trace.by_type("node_start")
vetoes = trace.by_type("judge_veto")

# Filter by node name
implement_events = trace.by_node("implement")

# All tool_call events, optionally filtered by tool name
all_calls = trace.tool_calls()
file_writes = trace.tool_calls("write_file")
```

### Reading trace events

```python
for e in result.trace.events:
    print(e.type, e.node, e.timestamp, e.data)

# Find all files written
writes = result.trace.tool_calls("write_file")
paths = [e.data["args"]["path"] for e in writes]

# Check veto reasons
for veto in result.trace.by_type("judge_veto"):
    print(f"  veto #{veto.data['veto_number']}: {veto.data['reason']}")
```
