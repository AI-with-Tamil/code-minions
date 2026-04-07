# RunContext

The spine of the SDK. Passed to every tool and deterministic node function.
Carries the environment, shared state, trace, model, config, and task.

## Interface

```python
from codeminions import RunContext

@dataclass
class RunContext(Generic[EnvT]):
    env:     EnvT                  # the active environment
    state:   BaseModel             # shared Pydantic state (typed via Blueprint[StateT])
    trace:   Trace                 # append-only execution trace
    model:   BaseModelProtocol     # the LLM (for ctx.ask())
    config:  RunConfig             # run-level config
    task:    Task                  # the full structured task
    run_id:  str                   # unique run identifier (uuid4)
    node:    str                   # name of the currently executing node
```

## Convenience methods

```python
# File operations — delegates to ctx.env
await ctx.read(path: str) -> str
await ctx.write(path: str, content: str) -> None
await ctx.exec(cmd: str, cwd: str | None = None) -> ExecResult

# Logging — appended to ctx.trace
ctx.log(message: str) -> None

# One-shot LLM call — does NOT add to agent conversation history
await ctx.ask(prompt: str, max_tokens: int = 512) -> str
```

## ExecResult

```python
@dataclass
class ExecResult:
    stdout:    str
    stderr:    str
    exit_code: int

    @property
    def ok(self) -> bool:
        return self.exit_code == 0
```

## RunConfig

```python
@dataclass
class RunConfig:
    max_concurrent:    int = 1
    token_budget:      int = 200_000   # total budget across all nodes in this run
    timeout_seconds:   int = 3600
    trace_level:       Literal["minimal", "full"] = "full"
```

## Typing

```python
# Untyped — ctx.state is BaseModel
async def my_fn(ctx: RunContext) -> None: ...

# Typed — ctx.state is CodingState, IDE autocomplete works
async def my_fn(ctx: RunContext[GitWorktreeEnv]) -> None:
    ctx.env.path        # type-checked as GitWorktreeEnv attribute
    ctx.state.branch    # type-checked as CodingState attribute
```

## Constraints

- `ctx` is constructed by the runner — never instantiated by user code
- `ctx.state` is mutable — nodes read and write to it freely
- `ctx.task` is immutable — no node can change the task
- `ctx.trace` is append-only — never modify trace entries
- `ctx.run_id` is stable across all nodes in a single run
- `ctx.node` changes as each node executes
