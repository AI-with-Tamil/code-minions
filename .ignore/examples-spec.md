# Minion SDK — Canonical Example Spec

> These examples are not marketing demos.
> They are the contract tests for the SDK design.
>
> If the SDK cannot express these examples cleanly, the public API is wrong.

---

## Why These Examples Exist

Minion SDK is a Python SDK for building **unattended coding workflows**.

The top-level abstraction is not a chat session and not a generic agent loop.
It is a **Blueprint**: a predefined coding workflow composed of node types.

Those node types are the real center of the system:

- `DeterministicNode`
- `AgentNode`
- `ParallelNode`
- `LoopNode`

Tools are attached to nodes.
State is shared across nodes.
The workflow produces branch-ready coding results.

These examples define the required public API, runtime behavior, result shape,
trace shape, and testing surface.

---

## Global Contracts

These examples assume the following core contracts exist.

### Core Primitives

```python
from minion import (
    Minion,
    Blueprint,
    DeterministicNode,
    AgentNode,
    ParallelNode,
    LoopNode,
    RunContext,
    RunResult,
    EscalationResult,
    RunConfig,
    tool,
)
```

### Supporting Public API

```python
from minion.models import ClaudeModel, OpenAIModel
from minion.environments import GitWorktreeEnv, LocalEnv, DockerEnv
from minion.tools import CODE_TOOLS, SHELL_TOOLS, CI_TOOLS
from minion.blueprints import coding_blueprint
from minion.testing import MockModel, MockEnvironment, run_blueprint_test
```

### Result Contract

```python
@dataclass
class RunResult:
    run_id: str
    outcome: Literal["passed", "failed", "escalated"]
    branch: str | None
    diff: str
    summary: str
    state: BaseModel
    trace: Trace
    tokens: int
    duration_ms: int
```

### Escalation Contract

```python
@dataclass
class EscalationResult(RunResult):
    node: str
    reason: str
    last_failure: str
```

### `RunContext` Contract

```python
@dataclass
class RunContext(Generic[EnvT]):
    env: EnvT
    state: BaseModel
    trace: Trace
    model: BaseModelProtocol
    config: RunConfig
    task: str
    run_id: str
    node: str

    async def read(self, path: str) -> str: ...
    async def write(self, path: str, content: str) -> None: ...
    async def exec(self, cmd: str) -> ExecResult: ...
    def log(self, message: str) -> None: ...
    async def ask(self, prompt: str, max_tokens: int = 512) -> str: ...
```

### Tool Contract

```python
@tool(description="...")
async def my_tool(ctx: RunContext, ...) -> ...:
    ...
```

Rules:
- first argument must always be `ctx: RunContext`
- no `*args` / `**kwargs`
- schema generated from typed parameters
- tool failures returned as structured tool results
- every `AgentNode` automatically receives a `done(...)` tool

### Node Contract

```python
class DeterministicNode:
    name: str
    fn: Callable[[RunContext], Awaitable[None] | None]
    condition: Condition | None = None
    on_failure: Literal["abort", "continue", "escalate"] = "escalate"

class AgentNode:
    name: str
    system_prompt: str
    tools: list[Tool]
    condition: Condition | None = None
    max_iterations: int = 80
    max_rounds: int = 1
    token_budget: int = 50_000
    on_max_rounds: Literal["escalate", "abort", "continue"] = "escalate"

class ParallelNode:
    name: str
    nodes: list[AnyNode]

class LoopNode:
    name: str
    sub_blueprint: Blueprint
    iterate_over: Callable[[RunContext], Iterable[Any]]
    bind: Callable[[RunContext, Any], None] | None = None
    max_iterations: int = 100
    on_failure: Literal["abort", "continue", "escalate"] = "continue"
```

---

## Example 1 — Sequential Coding Workflow

### Goal

Define the base unattended coding workflow:

`deterministic setup -> agent implementation -> deterministic finalize`

This is the minimum valid shape of the product.

### User Code

```python
from pydantic import BaseModel
from minion import Minion, Blueprint, DeterministicNode, AgentNode
from minion.tools import CODE_TOOLS, SHELL_TOOLS

class CodingState(BaseModel):
    branch: str = ""
    summary: str = ""
    outcome: str = "pending"

async def create_branch(ctx):
    ctx.state.branch = f"minion/{ctx.run_id}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")

async def commit_changes(ctx):
    await ctx.exec('git add -A && git commit -m "minion: complete task"')
    ctx.state.outcome = "passed"

blueprint = Blueprint(
    name="coding",
    state_cls=CodingState,
    nodes=[
        DeterministicNode("create_branch", fn=create_branch),
        AgentNode(
            "implement",
            system_prompt="Complete the task fully. Call done() when finished.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
        ),
        DeterministicNode("commit", fn=commit_changes),
    ],
)

result = await Minion(blueprint=blueprint).run(
    "Add validation for missing email in signup flow"
)
```

### What This Example Proves

- the SDK is workflow-first
- unattended coding is expressed as a predefined sequence
- `AgentNode` lives inside a workflow, not above it
- branch-oriented results are first-class

### Expected Runtime Flow

1. `create_branch` runs deterministically
2. `implement` starts an agent loop with code and shell tools
3. the agent calls `done(summary, files_changed)`
4. `commit` runs deterministically
5. a `RunResult` is returned

### Expected Result Shape

- `result.outcome == "passed"` on success
- `result.branch` is non-empty
- `result.summary` is sourced from `done(...)`
- `result.trace` includes node start/complete events

### Expected Trace Shape

- `node_start(create_branch)`
- `node_complete(create_branch)`
- `node_start(implement)`
- `tool_*` events within `implement`
- `node_complete(implement)`
- `node_start(commit)`
- `node_complete(commit)`

### Failure Semantics

- deterministic node failure -> fail or escalate based on policy
- agent budget exhaustion -> node failure
- missing `done()` -> treated as incomplete or budget failure

---

## Example 2 — Evaluator-Optimizer Coding Workflow

### Goal

Encode the standard unattended coding repair loop:

`implement -> lint -> fix_lint? -> test -> fix_tests?`

This is the core operational shape of Minion-like systems.

### User Code

```python
from pydantic import BaseModel
from minion import Blueprint, DeterministicNode, AgentNode, Minion
from minion.tools import CODE_TOOLS, SHELL_TOOLS

class CodingState(BaseModel):
    lint_failed: bool = False
    tests_failed: bool = False
    lint_output: str = ""
    test_output: str = ""

async def run_lint(ctx):
    result = await ctx.exec("ruff check . --fix")
    ctx.state.lint_failed = result.exit_code != 0
    ctx.state.lint_output = result.stdout

async def run_tests(ctx):
    result = await ctx.exec("pytest tests/ -x")
    ctx.state.tests_failed = result.exit_code != 0
    ctx.state.test_output = result.stdout

blueprint = Blueprint(
    name="coding_with_feedback",
    state_cls=CodingState,
    nodes=[
        AgentNode(
            "implement",
            system_prompt="Implement the requested change. Call done() when finished.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
        ),
        DeterministicNode("lint", fn=run_lint),
        AgentNode(
            "fix_lint",
            system_prompt="Fix lint errors only.",
            tools=CODE_TOOLS,
            condition=lambda ctx: ctx.state.lint_failed,
            max_rounds=1,
        ),
        DeterministicNode("test", fn=run_tests),
        AgentNode(
            "fix_tests",
            system_prompt="Fix failing tests only.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: ctx.state.tests_failed,
            max_rounds=2,
            on_max_rounds="escalate",
        ),
    ],
)

result = await Minion(blueprint=blueprint).run(
    "Add rate limiting to the login endpoint"
)
```

### What This Example Proves

- deterministic verification is first-class
- feedback loops belong in the workflow layer
- bounded retries are part of node semantics
- escalation is a core workflow outcome

### Expected Runtime Flow

1. `implement` runs
2. `lint` runs
3. `fix_lint` runs only if `lint_failed == True`
4. `test` runs
5. `fix_tests` runs only if `tests_failed == True`
6. if `fix_tests` exceeds allowed rounds, result escalates

### Expected Result Shape

- success path -> `RunResult(outcome="passed")`
- retry exhausted -> `EscalationResult(outcome="escalated")`

### Expected Trace Shape

- explicit skip events for conditional nodes when not needed
- explicit retry/re-entry tracking for fix nodes

### Failure Semantics

- failed lint/test command does not crash the workflow by default
- failure is encoded in shared state and consumed by later nodes
- `fix_tests` exhaustion must produce escalation, not silent looping

---

## Example 3 — Parallel Verification Workflow

### Goal

Demonstrate workflow-native parallelization for coding context gathering or verification.

### User Code

```python
from pydantic import BaseModel
from minion import Blueprint, DeterministicNode, ParallelNode, AgentNode, Minion
from minion.tools import CODE_TOOLS, SHELL_TOOLS

class GatherState(BaseModel):
    api_matches: str = ""
    test_matches: str = ""
    docs_matches: str = ""

async def search_api(ctx):
    result = await ctx.exec("rg -n 'signup|register' src/")
    ctx.state.api_matches = result.stdout

async def search_tests(ctx):
    result = await ctx.exec("rg -n 'signup|register' tests/")
    ctx.state.test_matches = result.stdout

async def search_docs(ctx):
    result = await ctx.exec("rg -n 'signup|register' docs/")
    ctx.state.docs_matches = result.stdout

blueprint = Blueprint(
    name="parallel_context",
    state_cls=GatherState,
    nodes=[
        ParallelNode(
            "gather_context",
            nodes=[
                DeterministicNode("search_api", fn=search_api),
                DeterministicNode("search_tests", fn=search_tests),
                DeterministicNode("search_docs", fn=search_docs),
            ],
        ),
        AgentNode(
            "implement",
            system_prompt="Use the gathered context to make the correct change. Call done() when finished.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
        ),
    ],
)

result = await Minion(blueprint=blueprint).run(
    "Fix inconsistent signup validation"
)
```

### What This Example Proves

- parallelization is a node-level workflow primitive
- the SDK can express focused context gathering cleanly
- shared state survives child-node parallel execution

### Expected Runtime Flow

1. all child nodes under `gather_context` run concurrently
2. state changes are merged deterministically
3. `implement` consumes the merged state

### Expected Trace Shape

- `node_start(gather_context)`
- nested start/complete events for each child node
- `node_complete(gather_context)`
- `node_start(implement)`

### Failure Semantics

- if one child fails, `ParallelNode` behavior must be defined
- default should likely be fail or escalate unless overridden

---

## Example 4 — Loop-Based Migration Workflow

### Goal

Demonstrate repeated application of a coding sub-workflow over dynamically discovered targets.

### User Code

```python
from pydantic import BaseModel
from minion import Blueprint, DeterministicNode, AgentNode, LoopNode, Minion
from minion.tools import CODE_TOOLS, SHELL_TOOLS

class MigrationState(BaseModel):
    targets: list[str] = []
    current_target: str | None = None
    migrated: list[str] = []
    failed: list[str] = []

async def discover_targets(ctx):
    result = await ctx.exec("rg -l 'OldAuthClient'")
    ctx.state.targets = [line for line in result.stdout.splitlines() if line.strip()]

async def validate_current(ctx):
    result = await ctx.exec(f"python -m py_compile {ctx.state.current_target}")
    if result.exit_code == 0:
        ctx.state.migrated.append(ctx.state.current_target)
    else:
        ctx.state.failed.append(ctx.state.current_target)

per_target = Blueprint(
    name="per_target",
    nodes=[
        AgentNode(
            "migrate_file",
            system_prompt="Migrate the current target to NewAuthClient without changing behavior.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
        ),
        DeterministicNode("validate_current", fn=validate_current),
    ],
)

migration = Blueprint(
    name="migration",
    state_cls=MigrationState,
    nodes=[
        DeterministicNode("discover_targets", fn=discover_targets),
        LoopNode(
            "apply_migration",
            sub_blueprint=per_target,
            iterate_over=lambda ctx: ctx.state.targets,
            bind=lambda ctx, item: setattr(ctx.state, "current_target", item),
            max_iterations=500,
        ),
    ],
)

result = await Minion(blueprint=migration).run(
    "Migrate OldAuthClient to NewAuthClient"
)
```

### What This Example Proves

- the SDK handles large repeated coding workflows
- `LoopNode` is a primary runtime primitive
- sub-blueprints are reusable workflow units

### Expected Runtime Flow

1. discover targets deterministically
2. iterate over each target
3. bind `current_target`
4. run sub-blueprint
5. aggregate success/failure into shared state

### Expected Result Shape

- `state.targets` populated
- `state.migrated` and `state.failed` reflect iteration outcomes

### Failure Semantics

- per-target failure handling must be explicit
- loop should not silently discard failures

---

## Example 5 — Fully Testable Workflow Contract

### Goal

Demonstrate that a complete coding workflow can be validated without real model calls.

### User Code

```python
from minion.blueprints import coding_blueprint
from minion.testing import (
    MockModel,
    MockEnvironment,
    ModelResponse,
    ToolCall,
    run_blueprint_test,
)

mock_model = MockModel(
    responses=[
        ModelResponse(tool_calls=[
            ToolCall("read_file", {"path": "src/auth.py"}),
            ToolCall("read_file", {"path": "tests/test_auth.py"}),
        ]),
        ModelResponse(tool_calls=[
            ToolCall("edit_file", {
                "path": "src/auth.py",
                "old": "return user.token",
                "new": "if user is None:\\n    return None\\nreturn user.token",
            }),
        ]),
        ModelResponse(tool_calls=[
            ToolCall("done", {
                "summary": "Added null guard in authenticate",
                "files_changed": ["src/auth.py"],
            }),
        ]),
    ]
)

env = MockEnvironment(
    files={
        "src/auth.py": "def authenticate(user):\\n    return user.token\\n",
        "tests/test_auth.py": "def test_authenticate_none(): ...\\n",
    },
    exec_results={
        "ruff check . --fix": 0,
        "pytest tests/ -x": 0,
    },
)

result = await run_blueprint_test(
    blueprint=coding_blueprint,
    task="Fix null handling in auth",
    model=mock_model,
    env=env,
)

result.assert_passed()
result.assert_node_ran("implement")
result.assert_tool_called("read_file", path="src/auth.py")
result.assert_tool_called("edit_file", path="src/auth.py")
result.assert_node_skipped("fix_lint")
result.assert_node_skipped("fix_tests")
```

### What This Example Proves

- the SDK is testable by design
- model behavior is mockable
- environment behavior is mockable
- workflow traces are stable enough for assertions
- examples double as real acceptance tests

### Expected Assertion Surface

```python
result.assert_passed()
result.assert_failed()
result.assert_escalated()
result.assert_node_ran(name)
result.assert_node_skipped(name)
result.assert_tool_called(name, **kwargs)
result.assert_tool_not_called(name)
result.assert_tokens_under(limit)
```

### Failure Semantics

- bad mock response shapes should fail clearly
- unsupported env operations should fail clearly
- assertion errors must be actionable

---

## What These 5 Examples Define

Together, these examples define the SDK as:

- workflow-first
- unattended-coding-first
- node-based
- tool-attached
- deterministic where possible
- agentic where necessary
- parallel and loop capable
- testable by design

This is the actual product boundary.

If the SDK cannot support these examples cleanly, it is not yet the right SDK.

---

## v1 Coverage

These examples imply the following v1 boundary.

### Must Exist in v1

- `Minion`
- `Blueprint`
- `DeterministicNode`
- `AgentNode`
- `ParallelNode`
- `LoopNode`
- `RunContext`
- `RunResult`
- `EscalationResult`
- `tool`
- `LocalEnv`
- `GitWorktreeEnv`
- `ClaudeModel` or one production model adapter
- `CODE_TOOLS`
- `SHELL_TOOLS`
- `coding_blueprint`
- `MockModel`
- `MockEnvironment`
- `run_blueprint_test`

### Can Be Deferred

- `DockerEnv`
- MCP tool loading
- remote environments
- JS CLI
- web UI
- advanced blueprint composition operators
- snapshot replay

---

## Final Design Rule

Do not ask:

> is this API simple enough for a demo?

Ask:

> does this API make unattended coding workflows explicit, testable, and predictable?

That is the real design standard for Minion SDK.
