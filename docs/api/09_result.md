# RunResult / EscalationResult

The output of a Minion run.

## RunResult

```python
from minion import RunResult

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
from minion import EscalationResult

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
