# Minion SDK — Deep Design Document

> A Python SDK for building unattended agentic coding harnesses, inspired by Stripe's Minions.

---

## What This Is

Not an agent. Not a framework. An **SDK** — a set of composable primitives that let developers
build their own Minion-like unattended coding agents.

The difference:
- LangGraph: you build a graph of nodes
- CrewAI: you build a crew of roles
- Minion SDK: you build a **Blueprint** — an ordered sequence of deterministic and agentic
  nodes that runs unattended, starts from a prompt, ends with a git branch

---

## The Five Core Primitives

```
Tool → Node → Blueprint → Environment → Minion
```

Everything else in the SDK is either an implementation of one of these primitives or a
supporting system (observability, storage, context loading, feedback).

---

## Primitive 1: Tool

A tool is a typed, decorated Python function that the LLM agent can call.
The first argument is always `RunContext[EnvT]` — dependency injection.

```python
from minion import tool, RunContext
from minion.environments import GitWorktreeEnv

@tool(description="Read a file from the workspace")
async def read_file(ctx: RunContext[GitWorktreeEnv], path: str) -> str:
    content = await ctx.env.read(path)
    ctx.trace.record_tool("read_file", {"path": path}, len(content))
    return content

@tool(description="Run a shell command and return stdout + stderr")
async def run_command(ctx: RunContext[GitWorktreeEnv], cmd: str) -> CommandResult:
    result = await ctx.env.exec(cmd)
    return CommandResult(stdout=result.stdout, stderr=result.stderr, exit_code=result.code)
```

### Tool Registry

Tools are registered globally or into named registries. Nodes declare which subset they need.

```python
from minion.tools import ToolRegistry

registry = ToolRegistry()

# Register individual tools
registry.register(read_file, write_file, edit_file, grep, glob)

# Named subsets — passed to AgentNode
CODE_TOOLS   = registry.subset(["read_file", "write_file", "edit_file", "grep", "glob"])
SHELL_TOOLS  = registry.subset(["run_command", "git_diff", "git_log", "git_status"])
CI_TOOLS     = registry.subset(["run_tests", "run_linter", "get_test_output"])
```

### Tool Schema Generation

When a tool is passed to an `AgentNode`, its schema is generated from the function signature
via introspection. Input types become JSON Schema. Output types are documented but not enforced
on the model — they're enforced on the Python side via Pydantic validation.

```python
# This function signature...
@tool(description="Search file contents")
async def grep(ctx: RunContext, pattern: str, path: str = ".", recursive: bool = True) -> list[GrepMatch]:
    ...

# ...generates this schema for the model:
{
  "name": "grep",
  "description": "Search file contents",
  "input_schema": {
    "type": "object",
    "properties": {
      "pattern": {"type": "string"},
      "path": {"type": "string", "default": "."},
      "recursive": {"type": "boolean", "default": true}
    },
    "required": ["pattern"]
  }
}
```

### Tool Execution Contract

- Tools receive `RunContext` — they never touch the environment directly
- Tool errors are caught, structured as `ToolError`, and fed back to the agent
- Tool results that exceed a size threshold are truncated with a note
- All tool calls are recorded in `ctx.trace` automatically by the runner (not the tool itself)
- Sync tools are supported — wrapped in `asyncio.run_in_executor` automatically

### MCP Tools

MCP servers can be exposed as tools in the registry:

```python
from minion.tools.mcp import MCPToolset

# Pull tools from an MCP server — filters by prefix
github_tools = MCPToolset(
    server="github-mcp",
    tools=["github.create_pr", "github.get_issue", "github.list_files"],
)

registry.register_mcp(github_tools)
```

---

## Primitive 2: Node

A node is one step in a Blueprint. Either deterministic (pure code, always same outcome)
or agentic (LLM loop, outcome is non-deterministic).

### DeterministicNode

Runs a Python callable. No LLM involved. Guaranteed to complete.
Sets state fields based on what the function returns.

```python
from minion import DeterministicNode

# Simple lambda
push = DeterministicNode(
    name="push_branch",
    fn=lambda ctx: ctx.env.exec("git push -u origin HEAD"),
)

# Full function with state mutation
async def run_linters(ctx: RunContext) -> dict:
    result = await ctx.env.exec("ruff check . --fix 2>&1")
    errors = parse_ruff_output(result.stdout)
    ctx.state.lint_failed = len(errors) > 0
    ctx.state.lint_errors = errors
    return {"lint_failed": ctx.state.lint_failed}

lint_node = DeterministicNode(name="lint", fn=run_linters)
```

### AgentNode

Runs an LLM loop. The agent can call any tool in its `tools` list, read context from
rule files encountered in the workspace, and mutate `ctx.state`.

```python
from minion import AgentNode

implement = AgentNode(
    name="implement",
    system_prompt="""
    You are an expert software engineer working in an isolated git worktree.
    Your task will be provided. Complete it fully. Write real, production-quality code.
    When done, call the `done` tool with a summary of what you changed.
    """,
    tools=CODE_TOOLS + SHELL_TOOLS,
    max_iterations=80,          # max LLM round trips
    token_budget=60_000,        # input + output token cap for this node
    condition=None,             # always runs (None = unconditional)
)

fix_lint = AgentNode(
    name="fix_lint_errors",
    system_prompt="Fix all lint errors listed in the context. Do not make other changes.",
    tools=CODE_TOOLS,
    max_iterations=20,
    token_budget=15_000,
    condition=lambda ctx: ctx.state.lint_failed,   # only runs if lint failed
    max_rounds=1,               # this node can only re-enter once (across CI loops)
)
```

### Node Lifecycle

```
condition check → [skip if false] → pre_hooks → execute → post_hooks → state update
```

Hooks let you inject logic around any node without modifying the Blueprint:

```python
@implement.on_start
async def log_start(ctx: RunContext):
    print(f"Starting implementation, worktree: {ctx.env.path}")

@implement.on_complete
async def record_diff(ctx: RunContext):
    ctx.state.diff = await ctx.env.exec("git diff HEAD")
```

### Node Types (Full Set)

| Node | Description |
|------|-------------|
| `DeterministicNode` | Pure function. No LLM. |
| `AgentNode` | LLM loop with tool calling. |
| `LoopNode` | Repeats a sub-Blueprint until condition is false or max_rounds hit. |
| `ParallelNode` | Runs multiple nodes concurrently, merges state on completion. |
| `ConditionalNode` | Branches to one of N sub-nodes based on state. |
| `HumanNode` | Pauses run and waits for human input (async, via SSE + response API). |

---

## Primitive 3: Blueprint

The Blueprint is the central primitive of this SDK. It is an ordered list of nodes that
represents the full lifecycle of a task — from receiving the prompt to pushing the branch.

### Why Ordered List, Not Graph

LangGraph uses an explicit graph (nodes + edges). This is flexible but requires understanding
graph theory and produces significant boilerplate.

A Blueprint uses an **ordered list with conditional skipping**. This matches how real agent
workflows are thought about: "do A, then B if needed, then always do C". The ordering is
the primary structure; conditions determine whether a step is skipped, not where to branch.

```python
from minion import Blueprint

coding_blueprint = Blueprint(
    name="coding",
    state_cls=CodingState,    # Pydantic model for shared state
    nodes=[
        DeterministicNode("gather_context",   fn=hydrate_context),
        AgentNode("implement",                tools=CODE_TOOLS + SHELL_TOOLS),
        DeterministicNode("lint",             fn=run_linters),
        AgentNode("fix_lint",                 tools=CODE_TOOLS, condition=lambda ctx: ctx.state.lint_failed),
        DeterministicNode("test",             fn=run_tests),
        AgentNode("fix_tests",                tools=CODE_TOOLS, condition=lambda ctx: ctx.state.tests_failed, max_rounds=2),
        DeterministicNode("commit",           fn=git_commit),
        DeterministicNode("push",             fn=git_push),
    ]
)
```

### Blueprint State

Every Blueprint has a `state_cls` — a Pydantic model that is shared across all nodes.
All nodes read from and write to the same state object via `ctx.state`.

```python
from pydantic import BaseModel

class CodingState(BaseModel):
    # Populated by gather_context
    task: str = ""
    repo_path: str = ""
    branch: str = ""

    # Populated by lint node
    lint_failed: bool = False
    lint_errors: list[str] = []

    # Populated by test node
    tests_failed: bool = False
    test_failures: list[str] = []
    ci_rounds: int = 0

    # Populated by push node
    pr_url: str | None = None
    outcome: str = "pending"   # pending | passed | failed | escalated
```

### Blueprint Execution Engine (Internal)

```python
class BlueprintEngine:
    async def run(
        self,
        blueprint: Blueprint,
        task: str,
        env: BaseEnvironment,
        model: BaseModel,
    ) -> RunResult:

        ctx = RunContext(
            env=env,
            state=blueprint.state_cls(task=task),
            trace=Trace(run_id=generate_id()),
            model=model,
            config=RunConfig(...),
        )

        for node in blueprint.nodes:
            # Condition check
            if node.condition is not None and not await node.condition(ctx):
                ctx.trace.record_skip(node.name)
                continue

            ctx.trace.record_node_start(node.name)

            try:
                if isinstance(node, DeterministicNode):
                    await node.fn(ctx)

                elif isinstance(node, AgentNode):
                    await self._run_agent_node(node, ctx)

                elif isinstance(node, LoopNode):
                    await self._run_loop_node(node, ctx)

                elif isinstance(node, ParallelNode):
                    await self._run_parallel_node(node, ctx)

            except NodeFailure as e:
                ctx.state.outcome = "failed"
                ctx.trace.record_failure(node.name, str(e))
                if node.on_failure == "escalate":
                    ctx.state.outcome = "escalated"
                    break
                elif node.on_failure == "abort":
                    break
                # "continue" — log and proceed

            ctx.trace.record_node_complete(node.name)

        return RunResult(
            run_id=ctx.trace.run_id,
            state=ctx.state,
            trace=ctx.trace,
            branch=ctx.state.branch,
            diff=await env.exec("git diff HEAD"),
        )
```

### Custom Blueprints

Blueprints are just Python objects. Users can extend them, compose them, or build entirely
custom ones for their use case:

```python
# Migration blueprint — specialized for codemod tasks
migration_blueprint = Blueprint(
    name="migration",
    state_cls=MigrationState,
    nodes=[
        DeterministicNode("discover_targets",  fn=find_migration_targets),
        AgentNode("plan",                      tools=READ_TOOLS, token_budget=10_000),
        LoopNode("apply",
            sub_blueprint=per_file_blueprint,
            iterate_over=lambda ctx: ctx.state.targets,
            max_iterations=100,
        ),
        DeterministicNode("validate",          fn=run_migration_tests),
        DeterministicNode("push",              fn=git_push),
    ]
)
```

---

## Primitive 4: Environment

The environment is where the agent's code changes live and where shell commands run.
It is the local equivalent of Stripe's devbox — an isolated execution context per task.

### BaseEnvironment Protocol

```python
from typing import Protocol

class BaseEnvironment(Protocol):
    path: str                          # root path of the workspace

    async def read(self, path: str) -> str: ...
    async def write(self, path: str, content: str) -> None: ...
    async def edit(self, path: str, old: str, new: str) -> None: ...
    async def exec(self, cmd: str, cwd: str | None = None) -> ExecResult: ...
    async def glob(self, pattern: str) -> list[str]: ...
    async def exists(self, path: str) -> bool: ...
    async def cleanup(self) -> None: ...
    async def snapshot(self) -> str: ...       # returns git diff / state hash
```

### GitWorktreeEnv

The primary environment for local Minion runs. Each run gets a separate git worktree
on a new branch. Worktrees are isolated at the filesystem level — separate `.git` index,
separate working directory, shared object store.

```python
from minion.environments import GitWorktreeEnv

env = GitWorktreeEnv(
    repo_path="./my-repo",
    base_branch="main",
    branch_prefix="minion",       # branches named minion/{task-id}
    pool_size=3,                  # pre-warm 3 worktrees
    cleanup_on_complete=True,
)
```

**Lifecycle:**

```
pool.warm() → [3 worktrees ready at main]
task arrives → pool.checkout() → assign worktree in < 100ms
agent runs → commits to minion/{id} branch
task done  → cleanup() or preserve for inspection
pool.refill() → spin up replacement worktree
```

**WorktreePool — internal design:**

```python
class WorktreePool:
    def __init__(self, repo_path: str, base_branch: str, size: int):
        self._repo_path = repo_path
        self._base_branch = base_branch
        self._pool: asyncio.Queue[Worktree] = asyncio.Queue()
        self._size = size

    async def warm(self):
        for _ in range(self._size):
            wt = await self._create_worktree()
            await self._pool.put(wt)

    async def checkout(self) -> Worktree:
        wt = await self._pool.get()
        asyncio.create_task(self._refill())    # immediately replace in background
        return wt

    async def _create_worktree(self) -> Worktree:
        branch = f"minion/warm-{generate_id()}"
        path = f"/tmp/minion-worktrees/{branch}"
        await run(f"git worktree add {path} -b {branch}", cwd=self._repo_path)
        return Worktree(path=path, branch=branch)
```

**Known limitation — runtime isolation:**
Worktrees isolate code (separate branch checkout) but NOT runtime (ports, databases, env vars).
For tasks that start services, use `DockerEnv` instead. For code-only tasks, `GitWorktreeEnv`
is sufficient and much lighter.

### DockerEnv

For tasks requiring service isolation (port conflicts, database state, etc.):

```python
from minion.environments import DockerEnv

env = DockerEnv(
    image="python:3.12",
    repo_mount="./my-repo:/workspace",
    working_dir="/workspace",
    env_file=".env.test",
    network="isolated",           # no outbound internet
    port_range=(40000, 50000),    # dynamic port assignment per container
)
```

### LocalEnv

No isolation — runs directly in the current directory. Useful for development/testing
of blueprints, or for simple single-task runs where isolation isn't needed:

```python
from minion.environments import LocalEnv

env = LocalEnv(path="./my-repo")
```

---

## Primitive 5: Minion (The Runner)

The `Minion` class ties model, blueprint, and environment together. It is the entry point
that users interact with.

```python
from minion import Minion
from minion.models import ClaudeModel
from minion.environments import GitWorktreeEnv

minion = Minion(
    model=ClaudeModel("claude-sonnet-4-6"),
    blueprint=coding_blueprint,
    environment=GitWorktreeEnv("./my-repo", pool_size=3),
    max_concurrent=5,             # max parallel runs
    storage="./minion-runs.db",   # SQLite path for run persistence
)

# Single run — async
result = await minion.run("Add rate limiting to the /api/users endpoint")

# Batch run — parallel
results = await minion.run_batch([
    "Fix flaky test in test_auth.py",
    "Add pagination to /api/posts",
    "Update the README with new API docs",
])

# Streaming run — events in real time
async for event in minion.run_stream("Fix the auth bug"):
    print(event)
```

---

## RunContext — Dependency Injection

Every tool and deterministic node function receives a `RunContext[EnvT]`.
This is the dependency injection mechanism — no global state, no singletons.

```python
from dataclasses import dataclass, field
from typing import Generic, TypeVar

EnvT = TypeVar("EnvT", bound=BaseEnvironment)

@dataclass
class RunContext(Generic[EnvT]):
    env: EnvT                     # the execution environment
    state: BaseState              # shared mutable state (Pydantic model)
    trace: Trace                  # observability — records everything
    model: BaseModel              # the LLM (accessible in deterministic nodes too)
    config: RunConfig             # token budgets, retry caps, timeouts
    task: str                     # the original task string
    run_id: str                   # unique ID for this run

    # Convenience passthrough to environment
    async def read(self, path: str) -> str:
        return await self.env.read(path)

    async def exec(self, cmd: str) -> ExecResult:
        result = await self.env.exec(cmd)
        return result

    # Convenience passthrough to trace
    def log(self, msg: str):
        self.trace.record_log(msg)
```

**Why `RunContext` instead of passing env/state separately?**
- Single argument to every function — consistent signature
- Can be extended by custom subclasses for domain-specific helpers
- Makes testing trivial — mock `RunContext`, test functions in isolation

---

## Agent Loop — Internal Design

The agent loop is what runs inside every `AgentNode`. It is the core LLM interaction
mechanism.

```python
class AgentLoop:
    def __init__(self, model: BaseModel, rules_loader: RuleLoader):
        self._model = model
        self._rules_loader = rules_loader

    async def run(self, node: AgentNode, ctx: RunContext) -> AgentResult:
        # Build initial messages
        messages = self._build_initial_messages(node, ctx)

        # Load rule files for context
        rules = self._rules_loader.load_for_path(ctx.env.path, ctx.env)
        system = self._build_system_prompt(node.system_prompt, rules, ctx)

        # Tool schemas for this node
        tool_schemas = [t.schema for t in node.tools]

        tokens_used = 0

        for iteration in range(node.max_iterations):
            # Check token budget
            if tokens_used >= node.token_budget:
                ctx.trace.record_budget_exhausted(node.name, tokens_used)
                break

            # LLM call
            response = await self._model.complete(
                messages=messages,
                tools=tool_schemas,
                system=system,
                max_tokens=min(4096, node.token_budget - tokens_used),
            )

            tokens_used += response.usage.total_tokens
            ctx.trace.record_llm_call(response.usage)

            # Agent signals completion
            if response.stop_reason == "end_turn" and not response.tool_calls:
                break

            # Execute tool calls (parallel when model supports it)
            if response.tool_calls:
                tool_results = await asyncio.gather(*[
                    self._execute_tool(call, node.tools, ctx)
                    for call in response.tool_calls
                ])
                messages = self._append_tool_results(messages, response, tool_results)
            else:
                messages.append({"role": "assistant", "content": response.content})

        ctx.trace.record_agent_complete(node.name, tokens_used, iteration + 1)
        return AgentResult(messages=messages, tokens=tokens_used, iterations=iteration + 1)

    async def _execute_tool(
        self,
        call: ToolCall,
        tools: list[Tool],
        ctx: RunContext,
    ) -> ToolResult:
        tool = next((t for t in tools if t.name == call.name), None)

        if tool is None:
            return ToolResult(id=call.id, error=f"Unknown tool: {call.name}")

        ctx.trace.record_tool_start(call.name, call.args)

        try:
            result = await tool.fn(ctx, **call.args)
            ctx.trace.record_tool_complete(call.name, result)
            return ToolResult(id=call.id, content=serialize_result(result))

        except Exception as e:
            ctx.trace.record_tool_error(call.name, str(e))
            return ToolResult(id=call.id, error=str(e))
```

### Context Pruning Between Nodes

When transitioning between `AgentNode`s, the conversation history from the previous node
is not passed forward by default. This prevents context bloat and keeps each node focused.

```python
class MemoryManager:
    def prune_for_node(
        self,
        history: list[Message],
        strategy: PruneStrategy,
    ) -> list[Message]:
        if strategy == PruneStrategy.CLEAR:
            return []                              # fresh start for next node
        elif strategy == PruneStrategy.SUMMARY:
            return [self._summarize(history)]      # single summary message
        elif strategy == PruneStrategy.KEEP_LAST_N:
            return history[-strategy.n:]           # rolling window
        elif strategy == PruneStrategy.KEEP_ALL:
            return history                         # full history (expensive)
```

Configurable per node:
```python
AgentNode(
    name="fix_tests",
    memory=PruneStrategy.SUMMARY,  # summarize what implement node did, pass forward
    ...
)
```

---

## Context System — Rule Files

Agents learn about a codebase through rule files that live in the repository.
The SDK loads them automatically as the agent traverses the filesystem.

### Rule Loader

```python
class RuleLoader:
    RULE_FILES = ["CLAUDE.md", "AGENTS.md", ".cursorrules", "MINION.md"]

    def load_for_path(self, start_path: str, env: BaseEnvironment) -> list[Rule]:
        rules = []
        current = start_path

        # Walk up the directory tree
        while current and current != "/":
            for filename in self.RULE_FILES:
                filepath = os.path.join(current, filename)
                if env.exists_sync(filepath):
                    content = env.read_sync(filepath)
                    rules.extend(self._parse(content, scope=current))
            current = os.path.dirname(current)

        return rules

    def _parse(self, content: str, scope: str) -> list[Rule]:
        # Parse frontmatter for conditional rules
        # ---
        # when: "*.py"
        # ---
        # Rule content...
        rules = []
        for section in split_frontmatter_sections(content):
            when = section.frontmatter.get("when")
            rules.append(Rule(
                content=section.body,
                when=when,        # None = unconditional
                scope=scope,
            ))
        return rules

    def filter_for_file(self, rules: list[Rule], filepath: str) -> list[Rule]:
        return [
            r for r in rules
            if r.when is None or fnmatch.fnmatch(filepath, r.when)
        ]
```

### Token-Aware Context Budget

Rule files are loaded but only injected into the system prompt if they fit within the
context budget. Least-specific rules (from higher directories) are trimmed first:

```python
def build_system_prompt(
    base_prompt: str,
    rules: list[Rule],
    token_budget: int,
) -> str:
    used = count_tokens(base_prompt)
    selected = []

    # Sort by specificity — deeper path = more specific = higher priority
    sorted_rules = sorted(rules, key=lambda r: r.scope.count("/"), reverse=True)

    for rule in sorted_rules:
        rule_tokens = count_tokens(rule.content)
        if used + rule_tokens <= token_budget:
            selected.append(rule)
            used += rule_tokens

    return base_prompt + "\n\n" + "\n\n".join(r.content for r in selected)
```

---

## Feedback Loop — Shift Left

The feedback loop is a first-class SDK primitive. It implements the tiered approach
Stripe uses: local lint → local tests → CI, with hard caps on retries.

### FeedbackLoop Builder

```python
from minion.feedback import FeedbackLoop

# Create a tiered feedback loop
feedback = FeedbackLoop(
    tiers=[
        FeedbackTier(
            name="lint",
            command="ruff check . --fix && ruff format .",
            timeout=5,
            autofix=True,               # run --fix, commit any changes
            on_failure="send_to_agent",  # feed errors to AgentNode
        ),
        FeedbackTier(
            name="tests",
            command="pytest {changed_files} --timeout=30 -x",
            timeout=60,
            file_selection=True,         # only test files related to changes
            autofix=False,
            on_failure="send_to_agent",
        ),
        FeedbackTier(
            name="ci",
            command="gh workflow run ci.yml --ref {branch}",
            wait_for_completion=True,
            timeout=600,
            max_rounds=2,                # Stripe's hard cap
            on_failure="escalate",       # after 2 rounds → escalate to human
        ),
    ]
)
```

### Failure Summarization

Raw CI output is too noisy for the agent. The feedback loop summarizes failures:

```python
class FailureSummarizer:
    async def summarize(
        self,
        tier: FeedbackTier,
        output: str,
        model: BaseModel,
    ) -> str:
        # For lint: just return the structured errors
        if tier.name == "lint":
            return parse_lint_errors(output)

        # For tests: extract test name + error + relevant stacktrace lines
        if tier.name == "tests":
            return parse_pytest_output(output)

        # For CI: use a small LLM call to extract the actionable failures
        if tier.name == "ci":
            return await self._llm_summarize(output, model)
```

### Autofix Detection

```python
AUTOFIX_MARKERS = {
    "ruff": "--fix",
    "black": "",           # black always fixes
    "prettier": "--write",
    "go fmt": "",
    "cargo fmt": "",
}

async def apply_autofixes(tier: FeedbackTier, env: BaseEnvironment) -> bool:
    if tier.autofix:
        result = await env.exec(tier.command_with_fix_flag)
        if result.exit_code == 0:
            await env.exec("git add -A && git commit -m 'chore: autofix lint'")
            return True
    return False
```

---

## Model Adapters

The SDK is model-agnostic. Models implement the `BaseModel` protocol.

### BaseModel Protocol

```python
from typing import Protocol

class BaseModel(Protocol):
    async def complete(
        self,
        messages: list[Message],
        tools: list[ToolSchema],
        system: str,
        max_tokens: int = 4096,
    ) -> ModelResponse: ...

    def count_tokens(self, messages: list[Message], tools: list[ToolSchema]) -> int: ...

    @property
    def context_window(self) -> int: ...

    @property
    def supports_parallel_tools(self) -> bool: ...

    @property
    def name(self) -> str: ...
```

### ClaudeModel

```python
class ClaudeModel:
    def __init__(
        self,
        model_id: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        enable_prompt_caching: bool = True,   # caches system prompt — saves tokens
        thinking: bool = False,               # enables extended thinking for complex tasks
    ):
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model_id = model_id
        self._cache = enable_prompt_caching

    async def complete(self, messages, tools, system, max_tokens=4096) -> ModelResponse:
        kwargs = {
            "model": self._model_id,
            "max_tokens": max_tokens,
            "system": self._build_system(system),
            "tools": [t.to_anthropic() for t in tools],
            "messages": [m.to_anthropic() for m in messages],
        }

        response = await self._client.messages.create(**kwargs)

        return ModelResponse(
            content=response.content,
            tool_calls=self._extract_tool_calls(response),
            stop_reason=response.stop_reason,
            usage=Usage(
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0),
            ),
        )

    @property
    def context_window(self) -> int:
        return 200_000

    @property
    def supports_parallel_tools(self) -> bool:
        return True
```

### OpenAIModel

Same protocol, different provider:

```python
class OpenAIModel:
    def __init__(self, model_id: str = "gpt-4o", api_key: str | None = None):
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model_id = model_id

    async def complete(self, messages, tools, system, max_tokens=4096) -> ModelResponse:
        response = await self._client.chat.completions.create(
            model=self._model_id,
            max_tokens=max_tokens,
            messages=[{"role": "system", "content": system}, *[m.to_openai() for m in messages]],
            tools=[t.to_openai() for t in tools],
        )
        return ModelResponse(...)

    @property
    def context_window(self) -> int:
        return 128_000

    @property
    def supports_parallel_tools(self) -> bool:
        return True
```

---

## Observability

Every run produces a structured trace. No extra code required — the SDK records everything
automatically at the runner level.

### Trace

```python
@dataclass
class Trace:
    run_id: str
    events: list[TraceEvent] = field(default_factory=list)
    _subscribers: list[Callable] = field(default_factory=list)

    def record_node_start(self, node: str):
        self._emit(TraceEvent(type="node_start", node=node, ts=now()))

    def record_node_complete(self, node: str, tokens: int = 0):
        self._emit(TraceEvent(type="node_complete", node=node, tokens=tokens, ts=now()))

    def record_node_skip(self, node: str):
        self._emit(TraceEvent(type="node_skip", node=node, ts=now()))

    def record_tool_start(self, tool: str, args: dict):
        self._emit(TraceEvent(type="tool_start", tool=tool, args=args, ts=now()))

    def record_tool_complete(self, tool: str, result_size: int):
        self._emit(TraceEvent(type="tool_complete", tool=tool, result_size=result_size, ts=now()))

    def record_tool_error(self, tool: str, error: str):
        self._emit(TraceEvent(type="tool_error", tool=tool, error=error, ts=now()))

    def record_llm_call(self, usage: Usage):
        self._emit(TraceEvent(type="llm_call", usage=usage, ts=now()))

    def record_log(self, message: str):
        self._emit(TraceEvent(type="log", message=message, ts=now()))

    def _emit(self, event: TraceEvent):
        self.events.append(event)
        for sub in self._subscribers:
            sub(event)

    def subscribe(self, fn: Callable):
        self._subscribers.append(fn)

    # Summary stats
    @property
    def total_tokens(self) -> int:
        return sum(e.usage.total_tokens for e in self.events if e.type == "llm_call")

    @property
    def total_tool_calls(self) -> int:
        return sum(1 for e in self.events if e.type == "tool_start")

    @property
    def duration_ms(self) -> int:
        return (self.events[-1].ts - self.events[0].ts) * 1000
```

### Event Subscription

```python
# On the Minion runner
@minion.on("node_start")
def log_node(event):
    print(f"[{event.node}] started")

@minion.on("tool_call")
def log_tool(event):
    print(f"  tool: {event.tool}({event.args})")

@minion.on("llm_call")
def log_tokens(event):
    print(f"  tokens: {event.usage.total_tokens}")
```

### Storage (SQLite)

```python
# schema
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    task TEXT NOT NULL,
    blueprint TEXT NOT NULL,
    outcome TEXT,                   -- pending | passed | failed | escalated
    branch TEXT,
    started_at REAL,
    completed_at REAL,
    total_tokens INTEGER,
    state_json TEXT                 -- full RunState as JSON
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    type TEXT NOT NULL,
    node TEXT,
    tool TEXT,
    data_json TEXT,
    ts REAL NOT NULL,
    FOREIGN KEY (run_id) REFERENCES runs(id)
);
```

---

## Error Handling and Escalation

### Error Types

```python
class NodeFailure(Exception):
    """A node failed and the blueprint should respond."""
    node: str
    reason: str
    recoverable: bool

class BudgetExhausted(NodeFailure):
    """Token budget for this node was exhausted."""
    tokens_used: int
    budget: int

class MaxRoundsReached(NodeFailure):
    """This node has been retried the maximum allowed times."""
    rounds: int
    last_failure: str

class ToolExecutionError(Exception):
    """A tool failed — fed back to the agent."""
    tool: str
    error: str
    args: dict
```

### Escalation Policy

When an `AgentNode` with `max_rounds=2` has exhausted its retries, the Blueprint
escalates instead of looping forever:

```python
AgentNode(
    name="fix_tests",
    max_rounds=2,
    on_max_rounds="escalate",    # options: escalate | abort | continue
)
```

`escalate` produces an `EscalationResult`:

```python
@dataclass
class EscalationResult:
    run_id: str
    node: str                    # which node gave up
    reason: str                  # why it gave up
    last_failure: str            # the failure it couldn't fix
    diff: str                    # changes made so far (still useful as starting point)
    branch: str                  # branch with the partial work
    trace: Trace                 # full trace for debugging
```

---

## RunConfig — Tunable Parameters

```python
@dataclass
class RunConfig:
    # Token limits
    default_token_budget: int = 50_000
    max_total_tokens: int = 500_000

    # Retry caps
    max_agent_iterations: int = 100
    max_ci_rounds: int = 2           # Stripe's number

    # Timeouts
    tool_timeout_s: int = 30
    node_timeout_s: int = 300
    run_timeout_s: int = 3600

    # Context
    max_rule_file_tokens: int = 10_000
    memory_strategy: PruneStrategy = PruneStrategy.SUMMARY

    # Feedback
    autofix_lint: bool = True
    autofix_tests: bool = True
    run_ci: bool = False             # disabled by default, opt-in

    # Parallelism
    max_concurrent_runs: int = 5
    max_parallel_tools: int = 4
```

---

## Complete Usage Example

```python
import asyncio
from pydantic import BaseModel as PydanticModel
from minion import (
    Minion, Blueprint,
    AgentNode, DeterministicNode,
    tool, RunContext,
)
from minion.models import ClaudeModel
from minion.environments import GitWorktreeEnv
from minion.tools import CODE_TOOLS, SHELL_TOOLS
from minion.feedback import FeedbackLoop

# --- Custom State ---

class CodingState(PydanticModel):
    task: str = ""
    branch: str = ""
    lint_failed: bool = False
    lint_errors: list[str] = []
    tests_failed: bool = False
    test_failures: list[str] = []
    outcome: str = "pending"
    pr_url: str | None = None


# --- Custom Tool ---

@tool(description="List all Python files modified in this run")
async def list_changed_files(ctx: RunContext[GitWorktreeEnv]) -> list[str]:
    result = await ctx.exec("git diff --name-only HEAD")
    return [f.strip() for f in result.stdout.splitlines() if f.endswith(".py")]


# --- Deterministic Node Functions ---

async def gather_context(ctx: RunContext):
    import uuid
    ctx.state.task = ctx.task
    ctx.state.branch = f"minion/{str(uuid.uuid4())[:8]}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")

async def run_linters(ctx: RunContext):
    result = await ctx.exec("ruff check . --fix 2>&1; ruff format .")
    errors = [l for l in result.stdout.splitlines() if "error" in l.lower()]
    ctx.state.lint_failed = result.exit_code != 0
    ctx.state.lint_errors = errors

async def run_tests(ctx: RunContext):
    result = await ctx.exec("pytest tests/ -x --timeout=30 -q 2>&1")
    ctx.state.tests_failed = result.exit_code != 0
    ctx.state.test_failures = parse_pytest_failures(result.stdout)

async def push_branch(ctx: RunContext):
    await ctx.exec(f"git push -u origin {ctx.state.branch}")
    ctx.state.outcome = "passed"


# --- Blueprint ---

coding_blueprint = Blueprint(
    name="coding",
    state_cls=CodingState,
    nodes=[
        DeterministicNode("gather_context",     fn=gather_context),
        AgentNode("implement",
            system_prompt="You are an expert software engineer. Complete the task fully. Call done() when finished.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS, list_changed_files],
            max_iterations=80,
            token_budget=60_000,
        ),
        DeterministicNode("lint",               fn=run_linters),
        AgentNode("fix_lint",
            system_prompt="Fix all lint errors. Do not make other changes.",
            tools=CODE_TOOLS,
            max_iterations=20,
            token_budget=15_000,
            condition=lambda ctx: ctx.state.lint_failed,
        ),
        DeterministicNode("test",               fn=run_tests),
        AgentNode("fix_tests",
            system_prompt="Fix the failing tests. Do not change test expectations unless they are wrong.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=30,
            token_budget=25_000,
            condition=lambda ctx: ctx.state.tests_failed,
            max_rounds=2,
            on_max_rounds="escalate",
        ),
        DeterministicNode("push",               fn=push_branch),
    ]
)


# --- Runner ---

minion = Minion(
    model=ClaudeModel("claude-sonnet-4-6"),
    blueprint=coding_blueprint,
    environment=GitWorktreeEnv("./my-repo", pool_size=3),
)

@minion.on("node_start")
def log_node(event):
    print(f"\n[{event.node}]")

@minion.on("tool_call")
def log_tool(event):
    print(f"  → {event.tool}")


# --- Run ---

async def main():
    result = await minion.run("Add rate limiting to the /api/users endpoint")

    print(f"\nOutcome:  {result.state.outcome}")
    print(f"Branch:   {result.state.branch}")
    print(f"Tokens:   {result.trace.total_tokens:,}")
    print(f"Duration: {result.trace.duration_ms}ms")

asyncio.run(main())
```

---

## Package Structure

```
minion/
├── __init__.py                  # full public API surface
│
├── core/
│   ├── tool.py                  # @tool decorator, Tool, ToolRegistry, ToolSchema
│   ├── node.py                  # BaseNode, AgentNode, DeterministicNode, LoopNode, ParallelNode
│   ├── blueprint.py             # Blueprint, BlueprintEngine
│   ├── context.py               # RunContext[EnvT], RunConfig, RunState
│   ├── result.py                # RunResult, EscalationResult, AgentResult
│   └── minion.py                # Minion runner
│
├── agent/
│   ├── loop.py                  # AgentLoop — core LLM tool-call loop
│   ├── rules.py                 # RuleLoader — CLAUDE.md, AGENTS.md, .cursorrules
│   └── memory.py                # MemoryManager — context pruning between nodes
│
├── models/
│   ├── base.py                  # BaseModel Protocol, Message, ModelResponse, Usage
│   ├── claude.py                # ClaudeModel (Anthropic SDK)
│   └── openai.py                # OpenAIModel
│
├── environments/
│   ├── base.py                  # BaseEnvironment Protocol, ExecResult
│   ├── worktree.py              # GitWorktreeEnv, WorktreePool, Worktree
│   ├── docker.py                # DockerEnv
│   └── local.py                 # LocalEnv
│
├── tools/
│   ├── __init__.py              # CODE_TOOLS, SHELL_TOOLS, CI_TOOLS, CONTEXT_TOOLS
│   ├── code.py                  # read_file, write_file, edit_file, create_file, delete_file
│   ├── shell.py                 # run_command, git_diff, git_log, git_status, git_commit
│   ├── search.py                # grep, glob, find_definition, find_usages
│   ├── ci.py                    # run_tests, run_linter, get_test_output
│   └── mcp.py                   # MCPToolset — pull tools from MCP servers
│
├── feedback/
│   ├── loop.py                  # FeedbackLoop, FeedbackTier
│   └── summarizer.py            # FailureSummarizer — converts raw CI output → agent input
│
├── storage/
│   └── db.py                    # SQLiteStorage — runs + events persistence
│
├── events.py                    # TraceEvent, EventEmitter, MinionEvent enum
├── trace.py                     # Trace — per-run event recording + stats
└── server.py                    # FastAPI + SSE — HTTP wrapper for CLI
```

### Public API (`minion/__init__.py`)

```python
# Core primitives
from minion.core.tool import tool, RunContext, ToolRegistry
from minion.core.node import AgentNode, DeterministicNode, LoopNode, ParallelNode
from minion.core.blueprint import Blueprint
from minion.core.context import RunConfig
from minion.core.result import RunResult, EscalationResult
from minion.core.minion import Minion

# Models
from minion.models.claude import ClaudeModel
from minion.models.openai import OpenAIModel

# Environments
from minion.environments.worktree import GitWorktreeEnv
from minion.environments.docker import DockerEnv
from minion.environments.local import LocalEnv

# Built-in tool subsets
from minion.tools import CODE_TOOLS, SHELL_TOOLS, CI_TOOLS, CONTEXT_TOOLS

# Feedback
from minion.feedback.loop import FeedbackLoop, FeedbackTier

# Events
from minion.events import MinionEvent
```

---

## JS CLI

The CLI is a thin Node.js consumer. It talks to `minion serve` via HTTP + SSE.

### Commands

```bash
minion run "Fix the flaky test in test_auth.py"
minion run "Add pagination to /users" --repo ./my-app --model claude-opus-4-6

minion list                    # table of active + recent runs
minion logs <id>               # live stream: nodes + tool calls + events
minion status <id>             # current node, tokens used, elapsed time
minion diff <id>               # git diff of all changes in this run
minion cancel <id>             # signal run to stop at next safe point
minion inspect <id>            # full trace as JSON
```

### Architecture

```
minion serve           →  FastAPI server (port 7777 by default)
                              /runs POST         start a run
                              /runs GET          list runs
                              /runs/{id} GET     run status
                              /runs/{id}/events  SSE stream
                              /runs/{id}/diff    git diff
                              /runs/{id} DELETE  cancel

minion (CLI)           →  Node.js + Commander.js
                              calls /runs to start
                              subscribes to /runs/{id}/events for live output
                              renders with Ink (React for terminals)
```

---

## Design Decisions

| Decision | Choice | Reason |
|----------|--------|--------|
| Blueprint = ordered list, not graph | List + conditions | Simpler mental model. 95% of workflows are sequential with optional steps. |
| State = Pydantic model | Pydantic BaseModel | Type safe, serializable, IDE-friendly |
| Dependency injection via RunContext | Single ctx arg | Consistent signature, easy mocking, no globals |
| Sync + async tools both supported | `run_in_executor` wrapping | Lower barrier for tool authors |
| Context pruning between nodes | SUMMARY by default | Prevents context bloat without losing task awareness |
| Rule files scoped to directories | Walk-up loader | Never flood context with all rules |
| Feedback hard-capped at 2 CI rounds | Configurable cap | Diminishing returns (Stripe + research confirmed) |
| SQLite for storage | Zero infra | Works locally, portable, queryable, no server needed |
| CLI in Node.js | Commander + Ink | Far better terminal UI primitives than Python |
| Model-agnostic via protocol | Protocol class | Swap providers without changing any Blueprint code |
| Worktree pool pre-warmed | asyncio.Queue | Sub-100ms environment checkout |
| Tools per-node, not global | Node.tools list | Smaller schema → fewer tokens per LLM call |

---

## What This Is NOT

- Not a chat agent UI
- Not a general-purpose workflow engine (that's Temporal/Prefect)
- Not a multi-agent framework with roles (that's CrewAI)
- Not a graph-based state machine (that's LangGraph)
- Not a cloud product — runs entirely local

---

## Build Phases

```
Phase 1 — Foundation (core primitives)
  core/tool.py       — @tool, ToolRegistry, ToolSchema
  core/node.py       — BaseNode, AgentNode, DeterministicNode
  core/blueprint.py  — Blueprint, BlueprintEngine
  core/context.py    — RunContext, RunConfig, RunState
  core/result.py     — RunResult, EscalationResult

Phase 2 — Agent Loop
  agent/loop.py      — AgentLoop with tool execution
  agent/rules.py     — RuleLoader
  agent/memory.py    — MemoryManager
  models/base.py     — BaseModel Protocol
  models/claude.py   — ClaudeModel

Phase 3 — Environments
  environments/base.py      — BaseEnvironment Protocol
  environments/worktree.py  — GitWorktreeEnv + WorktreePool
  environments/local.py     — LocalEnv

Phase 4 — Built-in Tools
  tools/code.py    — read_file, write_file, edit_file
  tools/shell.py   — run_command, git ops
  tools/search.py  — grep, glob

Phase 5 — Feedback Loop
  feedback/loop.py         — FeedbackLoop, FeedbackTier
  feedback/summarizer.py   — FailureSummarizer
  tools/ci.py              — run_tests, run_linter

Phase 6 — Storage + Events
  trace.py     — Trace
  events.py    — EventEmitter, MinionEvent
  storage/db.py — SQLiteStorage

Phase 7 — Minion Runner + Server
  core/minion.py   — Minion runner (ties everything)
  server.py        — FastAPI + SSE

Phase 8 — JS CLI
  cli/             — Commander + Ink
```
