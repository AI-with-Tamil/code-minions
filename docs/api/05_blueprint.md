# Blueprint

An ordered list of nodes defining the full lifecycle of a task.
Not a graph. Sequence with conditional skipping.

## Interface

```python
from minion import Blueprint
from pydantic import BaseModel

Blueprint(
    name:      str,
    nodes:     list[AnyNode],
    state_cls: type[BaseModel] | None = None,   # None = uses base RunState
)

# Typed shorthand
Blueprint[CodingState](
    name="coding",
    state_cls=CodingState,
    nodes=[...],
)
```

## State

Every Blueprint has a shared state object. All nodes read from and write to it.

```python
class CodingState(BaseModel):
    branch: str = ""
    lint_failed: bool = False
    lint_output: str = ""
    tests_failed: bool = False
    test_output: str = ""
    files_changed: list[str] = []
    pr_url: str = ""
```

Rules:
- `state_cls` must be a `pydantic.BaseModel` subclass
- All fields must have defaults (state is constructed with no arguments)
- State is serialized to JSON for storage and trace
- `None` state_cls → SDK uses a minimal `RunState(outcome: str = "pending")`

## Execution model

```python
for node in blueprint.nodes:
    if node.condition is not None and not node.condition(ctx):
        trace.record_skip(node.name)
        continue
    execute(node)   # DeterministicNode | AgentNode | JudgeNode | ParallelNode | LoopNode
```

Simple. No edges, no branches, no routing. Conditions control whether a step runs.

## Validation

Called automatically by `Minion.run()`. Can be called manually.

```python
blueprint.validate()
```

Checks:
- Node names are unique within the blueprint
- All `condition` functions have signature `(ctx: RunContext) -> bool`
- `JudgeNode.evaluates` references an existing `AgentNode` name
- `JudgeNode(on_veto="retry")` only targets `AgentNode`s with `max_rounds >= 2`
- `state_cls` is a valid Pydantic model with defaults on all fields
- `max_rounds >= 1` for all AgentNodes
- `ParallelNode` children are valid node types
- `LoopNode.sub_blueprint` is a valid Blueprint

Validation errors are actionable:

```
BlueprintValidationError: 2 issues in blueprint 'coding':

  1. Node 'fix_lint' (index 3): condition references ctx.state.lint_failed
     but 'lint_failed' is not defined in CodingState.
     Fix: add 'lint_failed: bool = False' to CodingState.

  2. Node 'review' (index 5): JudgeNode.evaluates='implement' but no
     AgentNode named 'implement' exists in this blueprint.
```

## Composition

```python
# Concatenate two blueprints
full = gather_blueprint + coding_blueprint

# Insert before/after named node
extended = coding_blueprint.before("push", security_scan_node)
extended = coding_blueprint.after("implement", format_node)

# Replace a node by name
custom = coding_blueprint.replace("implement", my_implement_node)

# Remove a node by name
headless = coding_blueprint.without("push")

# All composition methods return a NEW Blueprint — original is unchanged
```

## Built-in blueprints

```python
from minion.blueprints import coding_blueprint

# coding_blueprint nodes:
# create_branch → gather_context → implement → lint → fix_lint? →
# test → fix_tests? → commit → push → create_pr

# Use as-is
result = await Minion(blueprint=coding_blueprint).run(task)

# Use as base
my_blueprint = coding_blueprint.before("push", security_scan_node)
my_blueprint = coding_blueprint.replace("implement", my_implement_node)
```

## Blueprint as a type parameter

```python
# Typed — ctx.state is CodingState everywhere inside this blueprint
bp = Blueprint[CodingState](state_cls=CodingState, nodes=[...])

# Inside a node function:
async def my_fn(ctx: RunContext) -> None:
    ctx.state.lint_failed   # IDE knows this is bool
    ctx.state.branch        # IDE knows this is str
```
