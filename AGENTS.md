# Minion SDK — Agent Context

> Read this file first. It contains everything needed to understand and work on this project.
> This file is the single source of truth for any AI agent or developer working in this repo.

---

## What We Are Building

**Minion SDK** — a Python SDK for building unattended agentic coding harnesses.

Inspired by Stripe's internal system that ships 1,300+ PRs/week with zero human-written code.
This is not a product, not a chat agent, not a general workflow engine.

**One line:** The primitive layer that lets any engineering team build their own Stripe Minions.

**Who uses it:** Engineering teams at companies like Stripe, Ramp, Coinbase, Spotify — teams that
want to automate coding tasks (bug fixes, migrations, features) and have agents produce
reviewable PRs without human babysitting during execution.

**What it is NOT:**
- Not a chat agent UI
- Not LangGraph (no graph model)
- Not CrewAI (no role-based agents)
- Not a cloud product
- Not a general-purpose workflow engine (use Temporal for that)

---

## The Core Mental Model

```
Task → Blueprint → Branch
```

A **Task** comes in (string or structured). A **Blueprint** defines how to handle it.
A **Branch** (git) comes out — ready for human review.

The human reviews at the END, not during. The agent runs unattended.

---

## The Five Primitives

```
Tool → Node → Blueprint → Environment → Minion
```

### Tool
- `@tool` decorator, Pydantic-typed parameters
- First arg always `ctx: RunContext`
- Sync and async both supported
- Errors returned as structured results, never raised to Blueprint
- Output truncated above configurable threshold
- MCP servers load as tool sources (same contract)

### Node
Two types — the core insight from Stripe:
- `DeterministicNode(name, fn)` — pure Python, no LLM, guaranteed outcome
- `AgentNode(name, tools, system_prompt, ...)` — LLM loop with tool calling

Additional node types (v1):
- `JudgeNode(name, agent_node, criteria)` — LLM evaluates prior AgentNode output, can veto + retry
- `ParallelNode(name, nodes)` — runs child nodes concurrently, merges state
- `LoopNode(name, sub_blueprint, iterate_over, bind, ...)` — iterates a reusable sub-blueprint over discovered targets

Deferred to v2:
- `HumanNode` — contradicts "unattended", defer

Every `AgentNode` auto-receives a `done(summary, files_changed)` tool.
Agent must call `done()` to complete — explicit signal, not implicit end_turn.

`condition=lambda ctx: ctx.state.lint_failed` — node skipped if False.
`max_rounds=2` — how many times Blueprint can re-enter this node.
`on_max_rounds="escalate"` — what happens when rounds exhausted.

### Blueprint
- Ordered list of nodes — NOT a graph (intentional)
- 95% of real workflows are sequential with conditional steps
- `Blueprint(name, state_cls, nodes=[...])`
- Validates before running — clear errors on misconfiguration
- Composable: `a + b`, `.before(name, node)`, `.after(name, node)`, `.replace(name, node)`, `.without(name)`
- Built-in: `coding_blueprint` (ships with SDK, covers Stripe pattern out of the box)

### Environment
- Protocol-based structural typing — no inheritance required
- **`DockerEnv`** — PRIMARY for production. Full runtime isolation (ports, DBs, services).
- `GitWorktreeEnv` — local dev and testing only. Code isolation only, not runtime isolation.
- `LocalEnv` — no isolation, runs in cwd. For dev/testing blueprints only.

> IMPORTANT: Research across 17 companies shows every production system uses
> container/VM isolation (Stripe EC2, Ramp Modal, GitHub Actions ephemeral).
> Git worktrees are for lightweight local parallelism only.
> DockerEnv is the production path. Design accordingly.

### Minion (Runner)
- `Minion(model, blueprint, environment, config, storage, max_concurrent)`
- String shorthands: `model="claude-sonnet-4-6"`, `environment="docker"`, `blueprint="coding"`
- Zero-config: `Minion().run("Fix it")` works out of the box
- `await minion.run(task)` — single run
- `minion.run_sync(task)` — sync convenience
- `async for event in minion.run_stream(task)` — streaming
- `await minion.run_batch([...])` — parallel runs

---

## Task — Structured Input

Tasks are not just strings. Production systems inject rich context before the agent starts.

```python
from minion import Task

task = Task(
    description="Fix null check in authentication flow",
    context=["src/auth.py", "tests/test_auth.py"],         # files or URLs
    acceptance="pytest tests/test_auth.py passes",          # how we know it's done
    constraints=["Do not modify database migrations"],      # forbidden actions
)

# String shorthand still works
result = await Minion().run("Fix null check in auth")
```

This is LinkedIn's "specification-as-contract" pattern — structured spec beats free-form prompt
for reliability. Acceptance criteria gives the agent a binary signal for done.

---

## RunContext — The Spine

```python
@dataclass
class RunContext(Generic[EnvT]):
    env: EnvT                  # the environment (Docker, Worktree, Local)
    state: BaseModel           # shared Pydantic state across all nodes
    trace: Trace               # full execution trace
    model: BaseModelProtocol   # the LLM being used
    config: RunConfig          # run-level config
    task: Task                 # the full task (not just string)
    run_id: str                # unique run identifier
    node: str                  # current node name

    # Convenience methods
    async def read(self, path: str) -> str
    async def write(self, path: str, content: str) -> None
    async def exec(self, cmd: str) -> ExecResult
    def log(self, message: str) -> None
    async def ask(self, prompt: str, max_tokens: int = 512) -> str  # one-shot LLM call
```

---

## The Feedback Loop — Core Design

From Stripe (validated across all 17 companies):

```
Tier 0: Static/AST    < 100ms    import errors, parse failures
Tier 1: Lint          < 5s       ruff/eslint, autofix where possible
Tier 2: Tests         < 60s      related tests only (changed file → test mapping)
Tier 3: CI            minutes    max 2 rounds (Stripe hard cap), then escalate
```

Hard rules:
- Max 2 CI rounds. Never more. Diminishing returns proven empirically.
- Autofix applied deterministically before sending to agent.
- Failures summarized before sent to agent (not raw logs).
- After max_rounds exhausted → `EscalationResult`, not silent failure.

---

## JudgeNode — The Missing Primitive

From Spotify's Honk: LLM-as-judge vetoes 25% of agent outputs.
Agents self-correct 50% of the time when vetoed.
This is the difference between "code compiles" and "code is correct".

```python
JudgeNode(
    name="review",
    evaluates="implement",          # which AgentNode to evaluate
    criteria="Does the change match the task? No scope creep. No unrelated changes.",
    on_veto="retry",                # retry | escalate | continue
    max_vetoes=2,
)
```

---

## MCP — First Class

MCP is the universal tool bus. Stripe (~500 tools), Ramp, LinkedIn, Atlassian, Uber, GitHub Copilot all use it.

```python
from minion.tools.mcp import mcp_tools

AgentNode(
    "implement",
    tools=[
        *CODE_TOOLS,
        *mcp_tools("github", tools=["create_pr", "get_issue"]),
        *mcp_tools("sourcegraph", tools=["search_code"]),
    ]
)
```

MCP servers are just another tool source. Same `@tool` contract underneath.
Per-node tool curation is intentional — agents perform better with fewer, focused tools.

---

## RunResult

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

    # Actions
    def open_pr(self) -> str           # returns PR URL
    def push(self) -> None
    def inspect(self) -> None          # opens trace in CLI viewer

    # Test assertions
    def assert_passed(self) -> None
    def assert_tool_called(self, name: str, **kwargs) -> None
    def assert_node_skipped(self, name: str) -> None
    def assert_node_ran(self, name: str) -> None
    def assert_tokens_under(self, limit: int) -> None

@dataclass
class EscalationResult(RunResult):
    node: str           # which node triggered escalation
    reason: str         # why
    last_failure: str   # last error output
```

---

## Testing — First Class

No real API calls needed to test blueprints. Non-negotiable.

```python
from minion.testing import MockModel, MockEnvironment, run_blueprint_test

result = await run_blueprint_test(
    blueprint=coding_blueprint,
    task="Fix null check",
    model=MockModel(responses=[...]),
    env=MockEnvironment(files={"src/auth.py": "..."}, exec_results={"pytest": 0}),
)
result.assert_passed()
result.assert_tool_called("edit_file", path="src/auth.py")
result.assert_node_skipped("fix_lint")
```

---

## Package Structure

```
minion/
├── __init__.py                  # __all__ — the public API surface
├── core/
│   ├── tool.py                  # @tool, Tool, ToolRegistry
│   ├── node.py                  # AgentNode, DeterministicNode, JudgeNode, ParallelNode, LoopNode
│   ├── blueprint.py             # Blueprint[StateT], BlueprintEngine
│   ├── context.py               # RunContext[EnvT], RunConfig
│   ├── state.py                 # RunState base
│   ├── result.py                # RunResult, EscalationResult
│   ├── task.py                  # Task (structured input)
│   └── minion.py                # Minion runner
├── models/
│   ├── _base.py                 # BaseModelProtocol
│   ├── claude.py                # ClaudeModel
│   └── openai.py                # OpenAIModel
├── environments/
│   ├── _base.py                 # BaseEnvironment Protocol
│   ├── docker.py                # DockerEnv (PRIMARY — production)
│   ├── worktree.py              # GitWorktreeEnv (local dev only)
│   └── local.py                 # LocalEnv (dev/testing only)
├── tools/
│   ├── __init__.py              # CODE_TOOLS, SHELL_TOOLS, CI_TOOLS
│   ├── code.py                  # read_file, write_file, edit_file
│   ├── shell.py                 # run_command, git ops
│   ├── search.py                # grep, glob
│   ├── ci.py                    # run_tests, run_linter
│   └── mcp.py                   # mcp_tools() loader
├── blueprints/
│   └── coding.py                # coding_blueprint (default)
├── _internal/
│   ├── loop.py                  # AgentLoop (tool-call loop)
│   ├── rules.py                 # RuleLoader (CLAUDE.md, AGENTS.md, .cursorrules)
│   └── memory.py                # MemoryManager (context pruning)
├── storage/
│   └── db.py                    # SQLiteStorage (aiosqlite)
├── testing/
│   ├── mock_model.py
│   ├── mock_env.py
│   └── assertions.py
├── trace.py                     # Trace, TraceEvent
└── events.py                    # MinionEvent
```

---

## Public API — `__all__`

```python
# minion/__init__.py
from minion import (
    # Core
    Minion, Blueprint, Task,
    AgentNode, DeterministicNode, JudgeNode, ParallelNode, LoopNode,
    tool, RunContext, RunConfig, RunResult, EscalationResult,

    # Models
    ClaudeModel, OpenAIModel,

    # Environments
    DockerEnv, GitWorktreeEnv, LocalEnv,

    # Tool subsets
    CODE_TOOLS, SHELL_TOOLS, CI_TOOLS,

    # Built-in blueprints
    coding_blueprint,

    # Events
    MinionEvent,
)
```

---

## Zero-Config Defaults

```python
Minion().run("Fix it")  # works out of the box
```

Resolution order:
1. Explicit constructor args
2. `minion.toml`
3. `pyproject.toml [tool.minion]`
4. Environment variables (`MINION_MODEL`, etc.)
5. SDK defaults: `claude-sonnet-4-6`, `LocalEnv(".")`, `coding_blueprint`

Auto-detection:
- `ANTHROPIC_API_KEY` present → `ClaudeModel`
- `OPENAI_API_KEY` present → `OpenAIModel`
- `.git` found walking up from cwd → use as repo root

---

## Key Design Decisions (Locked)

| Decision | Choice | Reason |
|----------|--------|--------|
| Blueprint = ordered list | Not a graph | 95% of workflows are sequential + conditional |
| Async-first | asyncio throughout | Agent loops are inherently async |
| State = Pydantic BaseModel | Typed, serializable | IDE autocomplete, safe across nodes |
| Protocol-based env/model | Structural typing | No inheritance, easy to mock |
| `done()` tool explicit | Raises `_AgentDone` | Forces summary, clean signal |
| DockerEnv = primary | Not GitWorktreeEnv | Every production system uses container isolation |
| Task has structure | Not just a string | LinkedIn/Coinbase pattern — spec beats prompt |
| JudgeNode is a primitive | Not an afterthought | Spotify: 25% veto rate, real quality signal |
| LoopNode is a primitive | Not a custom helper | Airbnb migration pattern needs reusable per-target iteration |
| Max 2 CI rounds | Hard cap | Stripe-validated, diminishing returns proven |
| MCP = first class | `mcp_tools()` loader | Universal at every company doing this at scale |
| Testing = first class | `minion.testing` module | Can't validate SDK without real-API-free tests |
| No LangChain | Direct primitives | Keep deps minimal |

---

## v1 Build Phases

```
Phase 1 — Core primitives
  core/task.py, core/tool.py, core/node.py, core/blueprint.py
  core/context.py, core/state.py, core/result.py

Phase 2 — Agent loop + models
  _internal/loop.py, _internal/rules.py, _internal/memory.py
  models/claude.py

Phase 3 — Environments
  environments/docker.py (primary), environments/local.py, environments/worktree.py

Phase 4 — Built-in tools
  tools/code.py, tools/shell.py, tools/search.py, tools/ci.py, tools/mcp.py

Phase 5 — Feedback loop + runner
  core/minion.py (ties everything), blueprints/coding.py

Phase 6 — Storage + trace
  trace.py, events.py, storage/db.py

Phase 7 — Testing module
  testing/mock_model.py, testing/mock_env.py, testing/assertions.py

Phase 8 — CLI (deferred, v1.1)
```

---

## Examples (The Contract Tests)

The `examples/` folder contains 7 real-world usage examples based on company research.
These are not demos. They define what the SDK must be able to express.
If any example cannot be written cleanly, the API design is wrong.

| File | Based On | What It Tests |
|------|---------|---------------|
| `01_stripe_pattern.py` | Stripe Minions | Sequential: implement → lint → fix? → test → fix? → push |
| `02_spotify_judge.py` | Spotify Honk | JudgeNode: implement → judge evaluates → veto + retry or proceed |
| `03_airbnb_migration.py` | Airbnb RTL migration | LoopNode + per-file sub-blueprint: discover → apply → validate |
| `04_linkedin_spec.py` | LinkedIn agents | Structured Task with constraints and acceptance criteria |
| `05_anthropic_two_agent.py` | Anthropic internal | Two-agent: initializer → coder with progress handoff |
| `06_ramp_docker.py` | Ramp Inspect | DockerEnv with full-stack services running |
| `07_coinbase_council.py` | Coinbase Cloudbot | Agent council: primary + validator agent pair |

---

## Research Sources

Full research in `design/research/`:
- `stripe-blog.md` — Stripe Minions Parts 1 & 2 (primary inspiration)
- `anthropic-agent-guide.md` — Anthropic building effective agents guide
- `minion-research.md` — 7-direction gap validation
- `minion-company-research.md` — 17-company deep research
- `design/minion-sdk.md` — earlier SDK design document (reference only)

---

## How To Work On This Project

- Read this file first, always
- Examples in `examples/` are the source of truth for API design
- If examples force a primitive, update the docs and design explicitly rather than leaving contradictions around
- If an example looks awkward, the API is wrong — fix the API not the example
- `src/minion/` is the implementation — keep it aligned with examples and `docs/api/`
- Git/GitHub maintenance guidance lives in `docs/github-maintenance.md`
- Every new design decision gets added to this file
- New sessions: read `AGENTS.md` → read relevant example → start working
