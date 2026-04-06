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
from minion.environments import DockerEnv

DockerEnv(
    image:         str,                         # e.g. "python:3.12"
    repo_path:     str,                         # host path to mount
    working_dir:   str = "/workspace",
    env_file:      str | None = None,           # .env file to load
    network:       str = "none",                # "none" = no internet (safe default)
    port_range:    tuple[int, int] = (40000, 50000),  # dynamic port assignment
    memory_limit:  str = "4g",
    cpu_limit:     float = 2.0,
)
```

### Example

```python
env = DockerEnv(
    image="python:3.12-slim",
    repo_path="./my-repo",
    env_file=".env.test",
    network="none",
)
```

### Behavior

- Container created fresh per run — no shared state between runs
- `network="none"` blocks all outbound traffic (safe default for unattended agents)
- `exec()` runs inside the container
- Files written via `write()` are in the container's working directory
- `cleanup()` removes the container

---

## GitWorktreeEnv — Local Dev Only

Code isolation via git worktrees. Separate branch checkout per run.
Does NOT isolate ports, databases, or environment variables.
Use only for local development and testing blueprints.

```python
from minion.environments import GitWorktreeEnv

GitWorktreeEnv(
    repo_path:          str,
    base_branch:        str = "main",
    branch_prefix:      str = "minion",
    pool_size:          int = 1,             # pre-warmed worktrees
    cleanup_on_complete: bool = True,
)
```

### WorktreePool

```python
# Pre-warm a pool for parallel runs
env = GitWorktreeEnv(repo_path="./repo", pool_size=5)
await env.pool.warm()

# Each Minion.run() checks out a worktree in < 100ms
# Pool refills automatically in background after checkout
```

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
from minion.environments import LocalEnv

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
