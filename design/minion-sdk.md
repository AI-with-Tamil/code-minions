# Minion SDK — Deep Design Document

> Historical deep design reference.
> Current repo contract is defined by `AGENTS.md`, `docs/api/`, and `examples/`.
> If this document disagrees with those, the current contract wins.

> A Python SDK for building unattended agentic coding harnesses, inspired by Stripe's Minions.

---

## Thinking Like an SDK Builder

An SDK is not an app. An app optimizes for one user journey.
An SDK optimizes for **every** user journey its users will invent.

The job of an SDK designer is:

1. **Make the simple case trivially simple** — one import, one call, it works
2. **Make the complex case possible** — every primitive is extensible
3. **Never punish the user for choosing your SDK** — good errors, good types, good docs
4. **Earn trust** — predictable behavior, stable API, no surprises

The failure mode of most agent SDKs is: they solve the demo case beautifully and
collapse under real-world complexity. This SDK must not do that.

---

## API Design Principle: Progressive Disclosure

Users encounter the SDK in layers. Each layer should be satisfying on its own.
Users should never feel forced to understand the next layer before they're ready.

```python
# Layer 1 — Zero config. Just works. (5 minutes)
from minion import Minion

result = await Minion().run("Fix the flaky test in test_auth.py")
print(result.branch)

# Layer 2 — Configure the model and repo. (30 minutes)
result = await Minion(model="claude-opus-4-6", repo="./my-app").run("Fix it")

# Layer 3 — Custom blueprint. (a few hours)
from minion import Blueprint, AgentNode, DeterministicNode

blueprint = Blueprint(nodes=[...])
result = await Minion(blueprint=blueprint).run("Fix it")

# Layer 4 — Custom everything. (power users)
from minion import Minion, Blueprint, tool, RunContext
from minion.environments import GitWorktreeEnv

@tool(description="...")
async def my_tool(ctx: RunContext, arg: str) -> str: ...

result = await Minion(
    model=ClaudeModel("claude-opus-4-6"),
    blueprint=Blueprint(nodes=[AgentNode("implement", tools=[my_tool])]),
    environment=GitWorktreeEnv("./repo", pool_size=5),
).run("Fix it")
```

Every layer works independently. You never need to understand Layer 4 to use Layer 1.

---

## Zero-Config Defaults

`Minion()` with no arguments must work. The SDK resolves defaults in this order:

```
1. Explicit arguments    → Minion(model="claude-opus-4-6")
2. minion.toml           → [minion] model = "claude-opus-4-6"
3. pyproject.toml        → [tool.minion] model = "claude-opus-4-6"
4. Environment variables → MINION_MODEL=claude-opus-4-6
5. SDK defaults          → claude-sonnet-4-6, LocalEnv("."), coding blueprint
```

Auto-detection:
- **Model**: reads `ANTHROPIC_API_KEY` → ClaudeModel, `OPENAI_API_KEY` → OpenAIModel
- **Repo**: walks up from `cwd` until a `.git` directory is found
- **Blueprint**: `"coding"` — the built-in default coding blueprint
- **Environment**: `LocalEnv(".")` — no isolation, just works locally

---

## Package Design

### Minimal Dependencies

The SDK core must be installable with almost no transitive deps:

```toml
[project]
name = "minion-sdk"
dependencies = [
    "pydantic>=2.0",       # type safety — already everywhere
    "aiosqlite>=0.20",     # storage — lightweight
    "anyio>=4.0",          # async compatibility
]

[project.optional-dependencies]
claude  = ["anthropic>=0.50"]
openai  = ["openai>=1.0"]
docker  = ["docker>=7.0"]
cli     = ["rich>=13.0", "typer>=0.12"]
all     = ["anthropic>=0.50", "openai>=1.0", "docker>=7.0", "rich>=13.0", "typer>=0.12"]
```

```bash
pip install minion-sdk              # core only
pip install minion-sdk[claude]      # + Claude model
pip install minion-sdk[claude,cli]  # + Claude + CLI
pip install minion-sdk[all]         # everything
```

No LangChain. No LangGraph. No heavy frameworks in the dependency tree.

### Public API Surface — `__all__`

The public API is explicit and small. Everything not in `__all__` is internal (`_` prefix).

```python
# minion/__init__.py
__all__ = [
    # Core
    "Minion",
    "Blueprint",
    "AgentNode",
    "DeterministicNode",
    "JudgeNode",
    "LoopNode",
    "ParallelNode",
    "tool",
    "RunContext",
    "RunConfig",
    "RunResult",
    "EscalationResult",

    # Models
    "ClaudeModel",
    "OpenAIModel",

    # Environments
    "GitWorktreeEnv",
    "DockerEnv",
    "LocalEnv",

    # Built-in tool subsets
    "CODE_TOOLS",
    "SHELL_TOOLS",
    "CI_TOOLS",

    # Built-in blueprints
    "coding_blueprint",
    "migration_blueprint",
    "review_blueprint",

    # Events
    "MinionEvent",
]
```

Internal modules live under `minion._internal.*`. Never import from `_internal` in user code.
If users need something from internals, that's a signal the public API is missing something.

### Versioning

```
0.x.y  — Experimental. API may change between minor versions.
1.x.y  — Stable. Breaking changes only in major versions.
2.x.y  — Next major. Migration guide provided.
```

Deprecation policy: deprecated APIs emit `MinionDeprecationWarning` for one minor version
before removal.

---

## The Five Primitives — SDK Builder Perspective

### 1. Tool

#### Decorator Design

The `@tool` decorator must handle every realistic function signature cleanly:

```python
# Minimal — just works
@tool
async def read_file(ctx: RunContext, path: str) -> str: ...

# With description
@tool(description="Read a file from the workspace")
async def read_file(ctx: RunContext, path: str) -> str: ...

# With optional args and defaults
@tool(description="Search file contents with regex")
async def grep(ctx: RunContext, pattern: str, path: str = ".", recursive: bool = True) -> list[str]: ...

# Sync — automatically wrapped in executor
@tool(description="Compute something CPU-bound")
def compute(ctx: RunContext, data: str) -> str: ...

# Pydantic output type — serialized cleanly
@tool(description="Run tests and return structured result")
async def run_tests(ctx: RunContext, pattern: str = "tests/") -> TestResult: ...
```

#### What `@tool` Does At Import Time

```
1. Validate signature: first arg must be RunContext, no *args/**kwargs
2. Generate JSON Schema from remaining args via pydantic
3. Register in global registry (or local if registry= provided)
4. Return a Tool object (not the original function)
```

Fail at import time, not at runtime:
```python
@tool  # raises ToolDefinitionError immediately — not at runtime
async def bad_tool(*args):
    ...
# ToolDefinitionError: Tool 'bad_tool' cannot use *args.
# Tools must have explicit typed parameters.
```

#### Tool Output Handling

Large tool outputs are a real problem. File contents can be 100k+ tokens.

```python
class ToolOutputPolicy:
    max_chars: int = 50_000          # truncate above this
    truncation_msg: str = "... [truncated, {remaining} chars omitted]"
    structured_truncation: bool = True  # for list/dict outputs, truncate items
```

Users can override per-tool:
```python
@tool(description="Read a file", output_policy=ToolOutputPolicy(max_chars=10_000))
async def read_file(ctx: RunContext, path: str) -> str: ...
```

#### Tool Error Contract

Tool errors are returned to the agent as structured feedback, not raised as exceptions:

```python
# Inside the runner — never let tool errors crash the blueprint
try:
    result = await tool.fn(ctx, **call.args)
    return ToolResult(id=call.id, content=serialize(result))
except ToolError as e:
    # Structured error — agent can understand and react
    return ToolResult(id=call.id, error=e.message, recoverable=e.recoverable)
except Exception as e:
    # Unstructured error — wrap it
    return ToolResult(id=call.id, error=f"Tool '{tool.name}' failed: {str(e)}", recoverable=True)
```

The agent receives the error as a tool result and decides what to do.
Only completely unrecoverable errors (`recoverable=False`) escalate to the Blueprint.

---

### 2. Node

#### Node Is a Value, Not a Class Instance to Subclass

Nodes are configured via constructor args, not by subclassing. This is the Pydantic philosophy:
prefer configuration over inheritance.

```python
# Good — configuration
AgentNode(
    name="implement",
    tools=CODE_TOOLS,
    token_budget=60_000,
    condition=lambda ctx: not ctx.state.already_implemented,
)

# Bad — don't make users subclass
class ImplementNode(AgentNode):  # this should not be the pattern
    def should_run(self, ctx): ...
```

Exception: `DeterministicNode` takes a `fn` argument — users write functions, not subclasses.

#### The `done` Tool — Explicit Completion Signal

Every `AgentNode` automatically gets a `done` tool. The agent must call it to signal completion.
This is better than implicit completion (end_turn without tool calls) because:

- Forces the agent to produce a completion summary
- Gives a clean signal to the runner
- The summary is useful for the next node's context

```python
# Auto-injected into every AgentNode's tool list
@tool(description="Signal that you have completed your task")
async def done(
    ctx: RunContext,
    summary: str,                      # what was done
    files_changed: list[str] = [],     # which files were modified
    next_steps: str = "",              # optional — for human reviewer
) -> None:
    ctx.state.summary = summary
    ctx.state.files_changed = files_changed
    raise _AgentDone()                 # caught by runner, not an error
```

#### Node Conditions — Typed, Not Just Lambdas

Conditions can be lambdas or named predicate functions for reusability:

```python
from minion import when

# Lambda condition (inline)
AgentNode("fix_lint", condition=lambda ctx: ctx.state.lint_failed)

# Named predicate (reusable across nodes)
@when
def lint_failed(ctx: RunContext) -> bool:
    return ctx.state.lint_failed

AgentNode("fix_lint", condition=lint_failed)

# Combinators
AgentNode("fix_both", condition=lint_failed & tests_failed)
AgentNode("fix_either", condition=lint_failed | tests_failed)
AgentNode("skip_if_done", condition=~already_done)
```

#### Node Retry Policy

```python
AgentNode(
    name="fix_tests",
    max_rounds=2,                    # max times this node can re-execute
    on_max_rounds="escalate",        # escalate | abort | continue | skip
    retry_condition=lambda ctx: ctx.state.tests_failed,  # only retry if still failing
)
```

`max_rounds` is not the same as `max_iterations`:
- `max_iterations` = max LLM round-trips within one execution of the node
- `max_rounds` = max times the Blueprint can re-enter this node (across CI loop reruns)

---

### 3. Blueprint

#### Blueprint Is a Sequence, Not a Graph

The key design decision: Blueprint is an **ordered list of nodes**, not an arbitrary graph.

Why not a graph?
- 95% of real workflows are linear with conditional steps
- Graphs require understanding edges, which adds mental overhead
- "Do A, then B if needed, then always do C" maps naturally to a list
- Composition is simpler: `blueprint_a + blueprint_b`

When you need a graph → use LangGraph. That's the right tool for complex routing.
When you need an ordered workflow with optional steps → use Blueprint.

```python
# List semantics — this is the whole model:
# - Execute nodes in order
# - Skip nodes where condition evaluates to False
# - Re-enter nodes when max_rounds allows it (in feedback loops)
# - Stop and escalate on node failures if policy says so

Blueprint(nodes=[node1, node2, node3])
```

#### Blueprint Composition

Blueprints can be composed — concatenated, extended, or overridden:

```python
# Concatenate
full = gather_blueprint + implement_blueprint + ci_blueprint

# Extend (insert nodes before/after named node)
extended = coding_blueprint.before("push", security_scan_node)
extended = coding_blueprint.after("implement", format_node)

# Replace a node
custom = coding_blueprint.replace("implement", my_implement_node)

# Remove a node
headless = coding_blueprint.without("push")
```

#### Blueprint Validation

Blueprints validate before running — not at run time:

```python
blueprint.validate()
# Checks:
# - Node names are unique
# - All tool references exist in registry
# - State class is a valid Pydantic model
# - Condition functions have correct signature (ctx: RunContext) -> bool
# - No circular dependencies in LoopNode sub-blueprints
# - max_rounds >= 1 for all AgentNodes
```

Called automatically by `Minion.run()`. Can be called manually during development.

Validation errors are clear:

```
BlueprintValidationError: Blueprint 'coding' has 2 issues:

  1. Node 'fix_lint' (index 3): condition references ctx.state.lint_failed,
     but 'lint_failed' is not defined in state class CodingState.
     Add 'lint_failed: bool = False' to CodingState.

  2. Node 'implement' (index 1): tool 'search_code' is not registered.
     Available tools: read_file, write_file, edit_file, grep, glob, run_command
     Did you mean: grep?
```

#### Built-in Blueprints

Ship with 3 opinionated blueprints out of the box:

```python
from minion import coding_blueprint, migration_blueprint, review_blueprint

# coding_blueprint — the default
# gather → implement → lint → fix_lint? → test → fix_tests? → commit → push

# migration_blueprint — for codemods across many files
# gather → discover_targets → plan → apply(loop) → validate → push

# review_blueprint — read-only, produces a report
# gather → understand → analyze → report
```

Users can use them as-is or as a starting point:

```python
# Use as-is
result = await Minion(blueprint=coding_blueprint).run("Fix the bug")

# Use as starting point
my_blueprint = coding_blueprint.before("push", security_check_node)
```

#### Blueprint State — Generic Type Parameter

```python
# Untyped — ctx.state is RunState (base)
blueprint = Blueprint(nodes=[...])

# Typed — ctx.state is CodingState (your Pydantic model)
blueprint = Blueprint[CodingState](state_cls=CodingState, nodes=[...])

# IDE autocomplete now works on ctx.state.*
def my_fn(ctx: RunContext) -> None:
    ctx.state.lint_failed   # autocomplete, type-checked
    ctx.state.branch        # autocomplete, type-checked
```

---

### 4. Environment

#### BaseEnvironment Protocol (Structural Typing)

Users implement the protocol — no inheritance required:

```python
from typing import Protocol, runtime_checkable

@runtime_checkable
class BaseEnvironment(Protocol):
    path: str

    async def read(self, path: str) -> str: ...
    async def write(self, path: str, content: str) -> None: ...
    async def edit(self, path: str, old: str, new: str) -> None: ...
    async def exec(self, cmd: str, cwd: str | None = None) -> ExecResult: ...
    async def glob(self, pattern: str) -> list[str]: ...
    async def exists(self, path: str) -> bool: ...
    async def cleanup(self) -> None: ...
```

Any object with these methods works as an environment — no need to import `BaseEnvironment`.

#### GitWorktreeEnv — Lifecycle

GitWorktreeEnv is useful for local development and lightweight parallel testing.
It is not the production recommendation for unattended runs that need runtime isolation.

```python
env = GitWorktreeEnv(
    repo_path="./my-repo",         # path to the git repo
    base_branch="main",            # branch to checkout from
    branch_prefix="minion",        # branch names: minion/{run-id}
    pool_size=3,                   # pre-warmed worktrees
    pool_refill="eager",           # refill immediately on checkout
    cleanup="on_success",          # always | on_success | never
)
```

`cleanup="never"` is useful for debugging — inspect the worktree after a failed run.

#### Environment as Context Manager

```python
# Explicit lifecycle
async with GitWorktreeEnv("./repo") as env:
    result = await Minion(environment=env).run("Fix it")
# env.cleanup() called automatically

# Pool usage
pool = GitWorktreeEnv("./repo", pool_size=5)
await pool.warm()

async with pool.checkout() as env:
    result = await Minion(environment=env).run("Fix it")
# worktree returned to pool (or replaced if cleanup_on_success=True)
```

#### Custom Environment — Minimal Implementation

Users can build their own environment in ~30 lines:

```python
class S3Environment:
    """Reads/writes to S3. Useful for cloud-based agent runs."""

    def __init__(self, bucket: str, prefix: str):
        self.path = f"s3://{bucket}/{prefix}"
        self._s3 = boto3.client("s3")
        self._bucket = bucket
        self._prefix = prefix

    async def read(self, path: str) -> str:
        obj = self._s3.get_object(Bucket=self._bucket, Key=f"{self._prefix}/{path}")
        return obj["Body"].read().decode()

    async def write(self, path: str, content: str) -> None:
        self._s3.put_object(Bucket=self._bucket, Key=f"{self._prefix}/{path}", Body=content)

    async def exec(self, cmd: str, cwd=None) -> ExecResult:
        raise NotImplementedError("S3Environment does not support shell execution")

    # ... other methods
    async def cleanup(self) -> None:
        pass
```

---

### 5. Minion (The Runner)

#### Constructor — Flexible, Forgiving

```python
class Minion:
    def __init__(
        self,
        # Model — string shorthand or full object
        model: str | BaseModel = "claude-sonnet-4-6",

        # Blueprint — name, object, or None (uses default coding blueprint)
        blueprint: str | Blueprint | None = None,

        # Environment — path string, env type string, or full object
        environment: str | BaseEnvironment | None = None,

        # Shorthand for LocalEnv path
        repo: str | None = None,

        # Config overrides
        config: RunConfig | None = None,

        # Storage path — None = in-memory only
        storage: str | None = "~/.minion/runs.db",

        # Max parallel runs
        max_concurrent: int = 5,
    ):
```

String shorthands:
```python
Minion(model="claude-opus-4-6")           # → ClaudeModel("claude-opus-4-6")
Minion(model="gpt-4o")                    # → OpenAIModel("gpt-4o")
Minion(blueprint="coding")                # → built-in coding_blueprint
Minion(blueprint="migration")             # → built-in migration_blueprint
Minion(environment="worktree")            # → GitWorktreeEnv(".")
Minion(environment="docker")              # → DockerEnv(image="ubuntu:22.04")
Minion(repo="./my-app")                   # → LocalEnv("./my-app")
```

#### Run Methods — Sync and Async

```python
# Async (preferred)
result = await minion.run("Fix the auth bug")

# Sync convenience — wraps asyncio.run internally
result = minion.run_sync("Fix the auth bug")

# Streaming — yields events as they happen
async for event in minion.run_stream("Fix the auth bug"):
    print(event)

# Batch — parallel execution
results = await minion.run_batch([
    "Fix flaky test in test_auth.py",
    "Add pagination to /api/posts",
    "Update README with new API docs",
])

# Background — fire and forget, result via callback
run_id = await minion.run_background(
    "Fix the auth bug",
    on_complete=lambda result: send_slack(result.branch),
)
```

#### Event Hooks

```python
@minion.on(MinionEvent.NODE_START)
def on_start(event: NodeStartEvent):
    print(f"[{event.node}]")

@minion.on(MinionEvent.TOOL_CALL)
def on_tool(event: ToolCallEvent):
    print(f"  → {event.tool}({event.args})")

@minion.on(MinionEvent.LLM_CALL)
def on_llm(event: LLMCallEvent):
    print(f"  tokens: {event.usage.total_tokens}")

@minion.on(MinionEvent.RUN_COMPLETE)
def on_complete(event: RunCompleteEvent):
    print(f"Done: {event.outcome} ({event.total_tokens:,} tokens)")
```

---

## RunContext — The Injection Container

`RunContext` is the single object passed to every tool and deterministic node function.
It is the spine of the SDK — all state, environment, and observability flows through it.

```python
@dataclass
class RunContext(Generic[EnvT]):
    # Primary access points
    env: EnvT                         # the execution environment
    state: RunState                   # shared mutable state
    trace: Trace                      # observability
    model: BaseModel                  # the LLM (usable in deterministic nodes)
    config: RunConfig                 # budgets, caps, timeouts
    task: str                         # the original task string
    run_id: str                       # unique ID for this run
    node: str                         # current node name

    # Convenience shorthands (delegates to env)
    async def read(self, path: str) -> str:
        return await self.env.read(path)

    async def write(self, path: str, content: str) -> None:
        await self.env.write(path, content)

    async def exec(self, cmd: str) -> ExecResult:
        return await self.env.exec(cmd)

    # Convenience shorthands (delegates to trace)
    def log(self, msg: str) -> None:
        self.trace.record_log(msg)

    # One-shot LLM call (for deterministic nodes that need a small LLM call)
    async def ask(self, prompt: str, max_tokens: int = 512) -> str:
        response = await self.model.complete(
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            system="",
            max_tokens=max_tokens,
        )
        return response.text
```

#### Type Safety Through Generics

```python
# Untyped — env is BaseEnvironment
async def my_fn(ctx: RunContext) -> None:
    await ctx.exec("ls")  # works

# Typed — env is GitWorktreeEnv, IDE knows the specific type
async def my_fn(ctx: RunContext[GitWorktreeEnv]) -> None:
    await ctx.env.checkout("main")  # GitWorktreeEnv-specific method, autocompletes
```

---

## Testing — First-Class Citizen

This is where most SDKs fail. Testing an agent should not require real API calls.

### MockModel

```python
from minion.testing import MockModel, ToolCall, ModelResponse

mock = MockModel(
    responses=[
        # Turn 1: agent reads a file
        ModelResponse(tool_calls=[
            ToolCall("read_file", {"path": "src/auth.py"})
        ]),
        # Turn 2: agent edits the file
        ModelResponse(tool_calls=[
            ToolCall("edit_file", {"path": "src/auth.py", "old": "old code", "new": "new code"})
        ]),
        # Turn 3: agent signals done
        ModelResponse(tool_calls=[
            ToolCall("done", {"summary": "Fixed null pointer in auth"})
        ]),
    ]
)
```

### MockEnvironment

```python
from minion.testing import MockEnvironment

env = MockEnvironment(
    files={
        "src/auth.py": "def authenticate(user):\n    return user.token  # bug: no null check",
        "tests/test_auth.py": "def test_auth(): ...",
    }
)

# After run — inspect what the agent wrote
assert "if user is None" in env.files["src/auth.py"]
assert env.exec_calls == ["ruff check . --fix", "pytest tests/ -x"]
```

### Blueprint Test Helper

```python
from minion.testing import run_blueprint_test

result = await run_blueprint_test(
    blueprint=coding_blueprint,
    task="Fix the null check in auth.py",
    model=mock,
    env=MockEnvironment(files={"src/auth.py": "..."}),
)

# Rich assertions on the result
result.assert_passed()
result.assert_node_ran("implement")
result.assert_node_skipped("fix_lint")           # because lint passed
result.assert_tool_called("read_file", path="src/auth.py")
result.assert_tool_called("edit_file")
result.assert_tool_not_called("run_command")
result.assert_tokens_under(10_000)
```

### Snapshot Testing

```python
# Record a run against real API once — snapshot the trace
await result.snapshot("tests/snapshots/fix_auth_bug.json")

# Replay from snapshot — fast, no API calls, deterministic
from minion.testing import replay_snapshot
result = await replay_snapshot("tests/snapshots/fix_auth_bug.json")
result.assert_passed()
```

### Testing Deterministic Nodes in Isolation

```python
from minion.testing import make_context

# Test a deterministic node function directly
ctx = make_context(
    env=MockEnvironment(files={"src/auth.py": "..."}),
    state=CodingState(branch="test/branch"),
    task="Fix the null check",
)

await run_linters(ctx)

assert ctx.state.lint_failed == False
assert ctx.state.lint_errors == []
```

---

## Error Design

### Error Hierarchy

```python
# Base
class MinionError(Exception): ...

# Configuration errors — raised at setup time
class MinionConfigError(MinionError): ...     # bad Minion() args
class BlueprintValidationError(MinionError): ... # blueprint.validate() failed
class ToolDefinitionError(MinionError): ...   # bad @tool signature

# Runtime errors — raised during run
class NodeFailure(MinionError): ...           # a node failed
class BudgetExhausted(NodeFailure): ...       # token budget hit
class MaxRoundsReached(NodeFailure): ...      # retry cap hit
class ToolExecutionError(MinionError): ...    # tool raised an exception
class EnvironmentError(MinionError): ...      # env.exec() failed critically

# Result types — not exceptions, but outcomes
class RunResult: outcome: "passed" | "failed" | "escalated"
class EscalationResult(RunResult): reason: str; last_failure: str
```

### Actionable Error Messages

Every error must answer: **what happened, why, and how to fix it**.

```python
raise MinionConfigError(
    "No model configured and no API keys found.\n\n"
    "Options:\n"
    "  1. Pass a model:      Minion(model='claude-sonnet-4-6')\n"
    "  2. Set env var:       export ANTHROPIC_API_KEY=sk-...\n"
    "  3. Add to config:     echo 'model = \"claude-sonnet-4-6\"' >> minion.toml\n\n"
    "See: https://docs.minion-sdk.dev/getting-started"
)
```

```python
raise ToolDefinitionError(
    "Tool 'my_tool' has an invalid signature.\n\n"
    "  Got:      async def my_tool(arg: str) -> str\n"
    "  Expected: async def my_tool(ctx: RunContext, arg: str) -> str\n\n"
    "The first parameter must be 'ctx: RunContext' (or RunContext[YourEnv]).\n"
    "This gives the tool access to the execution environment and trace.\n\n"
    "See: https://docs.minion-sdk.dev/tools"
)
```

---

## Agent Loop — Internal Design

```python
class _AgentLoop:
    async def run(self, node: AgentNode, ctx: RunContext) -> None:
        messages: list[Message] = []

        # Build system prompt — base + scoped rule files (token-aware)
        system = ctx._rules.build_system(node.system_prompt, ctx.env.path, node.token_budget // 4)

        # Tool schemas — only this node's tools + auto-injected `done`
        tools = [*node.tools, _done_tool]
        schemas = [t.schema for t in tools]

        tokens_used = 0

        # Add task to first message
        messages.append(Message(role="user", content=f"Task: {ctx.task}"))

        for iteration in range(node.max_iterations):
            # Budget check
            remaining = node.token_budget - tokens_used
            if remaining < 500:
                ctx.log(f"[{node.name}] token budget nearly exhausted ({tokens_used}/{node.token_budget}), stopping")
                break

            # LLM call
            response = await ctx.model.complete(
                messages=messages,
                tools=schemas,
                system=system,
                max_tokens=min(4096, remaining),
            )

            tokens_used += response.usage.total_tokens
            ctx.trace.record_llm_call(response.usage, node=node.name)

            # No tool calls = model is done (shouldn't happen before done() is called)
            if not response.tool_calls:
                ctx.log(f"[{node.name}] model returned without tool calls — treating as done")
                break

            # Execute tool calls (parallel if model supports it)
            results = await self._execute_tools(response.tool_calls, tools, ctx)

            # Check for done signal
            if any(r.is_done_signal for r in results):
                ctx.trace.record_node_done(node.name, tokens_used, iteration + 1)
                return

            # Append results to conversation
            messages.append(Message(role="assistant", content=response.raw))
            messages.append(Message(role="user", content=format_tool_results(results)))

        ctx.trace.record_budget_exhausted(node.name, tokens_used)
```

### Parallel Tool Execution

```python
async def _execute_tools(
    self,
    calls: list[ToolCall],
    tools: list[Tool],
    ctx: RunContext,
) -> list[ToolResult]:
    if ctx.model.supports_parallel_tools and len(calls) > 1:
        # Execute all tool calls concurrently
        return await asyncio.gather(*[
            self._execute_one(call, tools, ctx) for call in calls
        ], return_exceptions=False)
    else:
        # Sequential fallback
        results = []
        for call in calls:
            results.append(await self._execute_one(call, tools, ctx))
        return results
```

---

## Context System — Rule Files

### RuleLoader

```python
class _RuleLoader:
    FILES = ["CLAUDE.md", "AGENTS.md", ".cursorrules", "MINION.md"]

    def load(self, workspace_path: str, env: BaseEnvironment) -> list[Rule]:
        rules = []
        path = workspace_path

        while path and path != os.path.dirname(path):   # stop at filesystem root
            for filename in self.FILES:
                full = os.path.join(path, filename)
                if env.exists_sync(full):
                    content = env.read_sync(full)
                    rules.extend(self._parse(content, scope=path))
            path = os.path.dirname(path)

        return rules

    def build_system(self, base_prompt: str, path: str, token_budget: int) -> str:
        rules = self.load(path, ...)
        # Sort by directory depth — deeper = more specific = higher priority
        rules.sort(key=lambda r: r.scope.count(os.sep), reverse=True)
        # Fill token budget greedily from most specific
        used = count_tokens(base_prompt)
        selected = []
        for rule in rules:
            cost = count_tokens(rule.content)
            if used + cost <= token_budget:
                selected.append(rule)
                used += cost
        return base_prompt + "\n\n" + "\n\n".join(r.content for r in selected)
```

### Conditional Rules (Frontmatter)

```markdown
---
when: "*.py"
priority: high
---
Always use type hints. Use `X | None` not `Optional[X]`.
Never use bare `except:`. Always specify the exception type.
```

```markdown
---
when: "tests/**"
---
Tests use pytest. Never use unittest.
Use `pytest.raises()` for exception assertions.
Mock external services with `respx` not `unittest.mock`.
```

---

## Feedback Loop — Shift Left

```python
from minion.feedback import FeedbackLoop, LintTier, TestTier, CITier

feedback = FeedbackLoop(
    tiers=[
        LintTier(
            name="lint",
            command="ruff check . --fix 2>&1 && ruff format .",
            timeout=10,
            autofix=True,            # apply --fix, commit result
        ),
        TestTier(
            name="tests",
            command="pytest {related_tests} -x --timeout=30 -q",
            timeout=60,
            related_test_detection=True,   # only run tests related to changed files
            autofix=False,
        ),
        CITier(
            name="ci",
            provider="github-actions",   # github-actions | gitlab-ci | circleci
            timeout=600,
            max_rounds=2,
            on_max_rounds="escalate",
        ),
    ]
)

# Attach to a Blueprint node
test_node = DeterministicNode("feedback", fn=feedback.run)
```

### Related Test Detection

```python
class RelatedTestDetector:
    """Maps changed source files to likely test files."""

    def detect(self, changed_files: list[str]) -> list[str]:
        test_files = []
        for src_file in changed_files:
            # src/auth/handler.py → tests/auth/test_handler.py
            # src/auth/handler.py → tests/test_auth_handler.py
            candidates = self._candidates(src_file)
            test_files.extend(f for f in candidates if self._env.exists(f))
        return test_files or ["tests/"]   # fallback to full suite
```

---

## RunResult — Rich Object

The result of a run is not just data. It has actions:

```python
@dataclass
class RunResult:
    run_id: str
    state: RunState
    trace: Trace
    branch: str | None
    outcome: str                    # passed | failed | escalated

    # Data access
    @property
    def diff(self) -> str:          # git diff of all changes
    @property
    def summary(self) -> str:       # agent's done() summary
    @property
    def tokens(self) -> int:        # total tokens used
    @property
    def duration_ms(self) -> int:   # wall-clock time

    # Actions (require env to be alive or stored)
    async def open_pr(self, title: str | None = None) -> str:  # returns PR URL
    async def push(self) -> None:                              # push branch if not already
    def inspect(self) -> None:                                 # open trace in browser
    async def replay(self) -> "RunResult":                     # re-run from stored trace

    # Testing assertions
    def assert_passed(self) -> "RunResult":
    def assert_failed(self) -> "RunResult":
    def assert_escalated(self) -> "RunResult":
    def assert_node_ran(self, name: str) -> "RunResult":
    def assert_node_skipped(self, name: str) -> "RunResult":
    def assert_tool_called(self, name: str, **kwargs) -> "RunResult":
    def assert_tool_not_called(self, name: str) -> "RunResult":
    def assert_tokens_under(self, limit: int) -> "RunResult":

    # Serialization
    def to_dict(self) -> dict:
    def to_json(self) -> str:
    @classmethod
    def from_json(cls, json_str: str) -> "RunResult":
```

---

## RunConfig — All Tunable Parameters

```python
@dataclass
class RunConfig:
    # Token limits
    default_token_budget: int = 50_000      # per AgentNode if not specified
    max_total_tokens: int = 500_000         # across entire run

    # Retry caps
    default_max_iterations: int = 80        # per AgentNode loop
    default_max_rounds: int = 1             # per AgentNode across Blueprint re-entries
    max_ci_rounds: int = 2                  # Stripe's number — hard cap

    # Timeouts
    tool_timeout_s: int = 30
    node_timeout_s: int = 600              # 10 minutes per node
    run_timeout_s: int = 3600             # 1 hour total

    # Context
    rules_token_budget_fraction: float = 0.25  # use at most 25% of node budget for rules
    memory_strategy: str = "summary"       # clear | summary | keep_last_n | keep_all
    memory_keep_last_n: int = 10           # if strategy is keep_last_n

    # Tools
    tool_output_max_chars: int = 50_000    # truncate large tool outputs
    parallel_tools: bool = True            # execute tool calls concurrently

    # Feedback
    autofix_lint: bool = True
    autofix_tests: bool = False
    run_ci: bool = False                   # opt-in — requires CI config

    # Parallelism
    max_concurrent_runs: int = 5
```

---

## CLI — Python First, Rich Terminal

Use Python CLI (not JS) for v1. Removes the Node.js dependency entirely.

```bash
pip install minion-sdk[claude,cli]

minion run "Fix the flaky test in test_auth.py"
minion run "Add pagination to /users" --model claude-opus-4-6 --repo ./my-app

minion list                  # rich table: id, task, node, outcome, tokens, time
minion logs <id>             # live stream with color
minion status <id>           # current node + token usage bar
minion diff <id>             # colored git diff
minion cancel <id>
minion inspect <id>          # full JSON trace
```

Built with `rich` + `typer`:
- `rich.live` for real-time node/tool display
- `rich.table` for `minion list`
- `rich.syntax` for `minion diff`
- `rich.progress` for token usage bar

JS CLI is v2 — a richer, interactive experience. Python CLI ships with the SDK itself.

---

## Configuration File

```toml
# minion.toml (or [tool.minion] in pyproject.toml)

[minion]
model = "claude-sonnet-4-6"
repo = "."
blueprint = "coding"
environment = "worktree"
storage = "~/.minion/runs.db"
max_concurrent = 5

[minion.worktree]
base_branch = "main"
pool_size = 3
branch_prefix = "minion"
cleanup = "on_success"

[minion.feedback]
lint_command = "ruff check . --fix"
test_command = "pytest tests/ -x --timeout=30"
max_ci_rounds = 2
run_ci = false

[minion.tokens]
default_budget = 50000
max_total = 500000

[minion.tools]
output_max_chars = 50000
parallel = true
```

---

## Observability — Trace Structure

```
Run {run_id}
├── node: gather_context
│   ├── [DeterministicNode]
│   └── duration: 120ms
│
├── node: implement
│   ├── [AgentNode] 23 iterations, 41,280 tokens
│   ├── tool: read_file("src/auth.py")          → 2.1kb
│   ├── tool: grep("def authenticate")           → 3 matches
│   ├── tool: read_file("tests/test_auth.py")    → 1.2kb
│   ├── tool: edit_file("src/auth.py", ...)      → ok
│   ├── tool: run_command("python -c 'import src.auth'") → ok
│   └── tool: done("Added null check in authenticate")
│
├── node: lint
│   ├── [DeterministicNode]
│   ├── exec: ruff check . --fix → 0 errors
│   └── state: lint_failed=False
│
├── node: fix_lint → SKIPPED (condition: lint_failed=False)
│
├── node: test
│   ├── [DeterministicNode]
│   ├── exec: pytest tests/test_auth.py -x → 1 passed
│   └── state: tests_failed=False
│
├── node: fix_tests → SKIPPED (condition: tests_failed=False)
│
└── node: push
    ├── [DeterministicNode]
    ├── exec: git commit -m "fix: add null check in authenticate"
    ├── exec: git push -u origin minion/a3f21b
    └── state: outcome=passed

Total: 41,280 tokens | 4m 12s | passed
```

---

## Package Structure (Final)

```
minion/
├── __init__.py                  # public API + __all__
│
├── _internal/                   # private — never import from user code
│   ├── loop.py                  # AgentLoop
│   ├── engine.py                # BlueprintEngine
│   ├── rules.py                 # RuleLoader
│   ├── memory.py                # MemoryManager
│   ├── schema.py                # JSON Schema generation from @tool
│   └── resolve.py               # string → object resolution (model names, etc.)
│
├── core/
│   ├── tool.py                  # tool, Tool, ToolRegistry, when
│   ├── node.py                  # AgentNode, DeterministicNode, JudgeNode, LoopNode, ParallelNode
│   ├── blueprint.py             # Blueprint[StateT]
│   ├── context.py               # RunContext[EnvT], RunConfig
│   ├── state.py                 # RunState (base Pydantic model)
│   ├── result.py                # RunResult, EscalationResult
│   └── minion.py                # Minion
│
├── models/
│   ├── _base.py                 # BaseModel Protocol, Message, ModelResponse, Usage
│   ├── claude.py                # ClaudeModel
│   └── openai.py                # OpenAIModel
│
├── environments/
│   ├── _base.py                 # BaseEnvironment Protocol, ExecResult
│   ├── worktree.py              # GitWorktreeEnv, WorktreePool
│   ├── docker.py                # DockerEnv
│   └── local.py                 # LocalEnv
│
├── tools/
│   ├── __init__.py              # CODE_TOOLS, SHELL_TOOLS, CI_TOOLS exports
│   ├── code.py                  # read_file, write_file, edit_file, create_file
│   ├── shell.py                 # run_command, git_diff, git_log, git_status, git_commit
│   ├── search.py                # grep, glob, find_definition
│   └── ci.py                    # run_tests, run_linter
│
├── blueprints/
│   ├── __init__.py              # coding_blueprint, migration_blueprint, review_blueprint
│   ├── coding.py                # default coding blueprint + its state
│   ├── migration.py
│   └── review.py
│
├── feedback/
│   ├── loop.py                  # FeedbackLoop, LintTier, TestTier, CITier
│   ├── summarizer.py            # FailureSummarizer
│   └── detection.py             # RelatedTestDetector
│
├── testing/
│   ├── __init__.py              # MockModel, MockEnvironment, run_blueprint_test
│   ├── mock_model.py
│   ├── mock_env.py
│   └── assertions.py            # result assertion helpers
│
├── storage/
│   └── db.py                    # SQLiteStorage
│
├── trace.py                     # Trace, TraceEvent
├── events.py                    # MinionEvent enum, EventEmitter
├── errors.py                    # full error hierarchy
├── config.py                    # RunConfig, config file loading
└── cli/
    ├── __init__.py
    ├── main.py                  # typer app
    └── display.py               # rich rendering
```

---

## What v1 Ships vs What Comes Later

### v1 Ships
- `Minion`, `Blueprint`, `AgentNode`, `DeterministicNode`
- `JudgeNode`, `ParallelNode`, `LoopNode`
- `@tool`, `RunContext`, `RunConfig`, `RunResult`
- `ClaudeModel`, `OpenAIModel`
- `DockerEnv`, `GitWorktreeEnv`, `LocalEnv`
- Built-in tools: `CODE_TOOLS`, `SHELL_TOOLS`, `CI_TOOLS`
- Built-in blueprints: `coding_blueprint`
- MCP tool integration
- Feedback loop with bounded lint + test + CI retries
- Testing: `MockModel`, `MockEnvironment`, `run_blueprint_test`
- SQLite storage
- Python CLI (`rich` + `typer`)
- Zero-config defaults

### Post-v1
- `migration_blueprint`, `review_blueprint`
- Snapshot-based replay testing
- JS CLI (rich interactive terminal)
- Web UI for trace visualization
- Blueprint composition operators (`>>`, `+`)
- Remote environments (cloud VMs)

---

## What This Is NOT

- Not a chat agent UI
- Not a general-purpose workflow engine (use Temporal or Prefect)
- Not a multi-agent framework with roles (use CrewAI)
- Not a graph-based state machine (use LangGraph)
- Not a cloud product — runs entirely local

The SDK is intentionally narrow. It solves one problem well:
**building unattended coding agents that go from prompt to git branch.**
