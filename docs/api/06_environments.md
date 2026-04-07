# Environments

Where the agent's code changes live and where shell commands execute.
One environment instance per Minion run.

## BaseEnvironment Protocol

Structural typing — no inheritance required. Any object with these methods works.

```python
class BaseEnvironment(Protocol):
    path: str                  # root working directory

    async def read(self, path: str) -> str
    async def write(self, path: str, content: str) -> None
    async def edit(self, path: str, old: str, new: str) -> None
    async def exec(self, cmd: str, cwd: str | None = None) -> ExecResult
    async def glob(self, pattern: str) -> list[str]
    async def exists(self, path: str) -> bool
    async def cleanup(self) -> None
```

---

## DockerEnv — Production Primary

Full runtime isolation. One container per run. Ports, databases, services all isolated.
Use this for production agents and any task that starts services.

```python
from codeminions.environments import DockerEnv

DockerEnv(
    image:            str,                         # e.g. "python:3.12"
    repo_path:        str,                         # host path to mount
    working_dir:      str = "/workspace",
    env_file:         str | None = None,           # .env file to load
    network:          str = "none",                # "none" = no internet (safe default)
    port_range:       tuple[int, int] = (40000, 50000),  # dynamic port assignment
    memory_limit:     str = "4g",
    cpu_limit:        float = 2.0,
    startup_commands: list[str] = [],             # run inside container before agent starts
)
```

### Example

```python
env = DockerEnv(
    image="python:3.12-slim",
    repo_path="./my-repo",
    env_file=".env.test",
    network="none",
    startup_commands=[
        "pip install -e '.[dev]'",
        "python -c 'import app; print(\"app ready\")'",
    ],
)
```

The startup commands run inside the container before any agent node executes. If a command fails, `setup()` raises `RuntimeError` immediately and cleans up the container.

### Behavior

- Container created fresh per run — no shared state between runs
- `network="none"` blocks all outbound traffic (safe default for unattended agents)
- `exec()` runs inside the container via `sh -c`; callers must `shlex.quote()` any user-supplied values
- `write()` uses `put_archive` (no shell) — safe for any file content including single quotes and binary
- `env_file` is parsed and injected as container environment variables at startup
- `port_range` reserves a free host port at setup time; use `env._reserved_port` for service binding
- `startup_commands` run sequentially after container creation; any non-zero exit aborts setup with a clear error
- `cleanup()` removes the container

---

## GitWorktreeEnv — Local Dev Only

Code isolation via git worktrees. Separate branch checkout per run.
Does NOT isolate ports, databases, or environment variables.
Use only for local development and testing blueprints.

```python
from codeminions.environments import GitWorktreeEnv

GitWorktreeEnv(
    repo_path:          str,
    base_branch:        str = "main",
    branch_prefix:      str = "minion",
    pool_size:          int = 1,             # pre-warmed worktrees
    cleanup_on_complete: bool = True,
)
```

### WorktreePool

When `pool_size > 1`, `GitWorktreeEnv` creates a `WorktreePool` that manages pre-warmed worktrees for parallel runs.

```python
env = GitWorktreeEnv(repo_path="./repo", pool_size=4)

# Pre-create 4 worktrees (call before run_batch)
await env.pool.warm()

# run_batch draws from the pool — each run checks out in < 100ms
results = await Minion(environment=env).run_batch(tasks)

# Remove remaining pooled worktrees when done
await env.pool.close()
```

Pool lifecycle:
- `warm()` — pre-creates `pool_size` worktrees on the base branch
- `acquire()` — returns a ready worktree; creates one on demand if queue is empty
- `release(path, branch)` — resets and returns the worktree to the queue, or removes if at capacity
- `close()` — removes all queued worktrees (best-effort)

`pool_size=1` (default) skips the pool — each run creates and removes its own worktree. Accessing `env.pool` raises `RuntimeError` when `pool_size=1`.

### Limitation

Worktrees isolate code (separate branch checkout) but NOT runtime.
If two agents both try to bind `localhost:3000`, they conflict.
For runtime isolation, use `DockerEnv`.

---

## LocalEnv — Dev And Testing Only

No isolation. Runs directly in the specified directory.
Use for local development, example workflows, and blueprint testing.
Do not treat it as a production unattended environment.

```python
from codeminions.environments import LocalEnv

LocalEnv(path: str = ".")
```

---

## Environment string shorthands

```python
Minion(environment="docker")    # DockerEnv with defaults
Minion(environment="worktree")  # GitWorktreeEnv with defaults
Minion(environment="local")     # LocalEnv(".")
```

---

## Running example 09

End-to-end validation against a real LLM:

```bash
# 1. Set up credentials
cp .env.example .env
# edit .env — fill in ANTHROPIC_API_KEY (or OPENAI_API_KEY)

# 2. Run
uv run python examples/validation/09_real_repo_config_resolution.py
```

**Expected output:**

```
model      : claude-sonnet-4-6
outcome    : passed
branch     : codeminions-real-<hash>
worktree   : /path/to/worktree
tokens     : <number>
duration   : <ms>
summary    : <agent summary>
acceptance : True

--- diff ---
<non-empty diff showing changes to src/codeminions/>
```

**Verification checklist:**

- `outcome: passed` (not escalated)
- `branch: codeminions-real-*` — worktree branch was created
- `diff` is non-empty — agent wrote code
- `acceptance: True` — pytest -k ConfigurationResolution passed in worktree
- Worktree path exists on disk for manual inspection (cleanup_on_complete=False)

---

## Custom environment

Any class implementing `BaseEnvironment` protocol works:

```python
class MyCloudEnv:
    path = "/workspace"

    async def exec(self, cmd, cwd=None) -> ExecResult: ...
    async def read(self, path) -> str: ...
    async def write(self, path, content) -> None: ...
    async def edit(self, path, old, new) -> None: ...
    async def glob(self, pattern) -> list[str]: ...
    async def exists(self, path) -> bool: ...
    async def cleanup(self) -> None: ...

result = await Minion(environment=MyCloudEnv()).run(task)
```
