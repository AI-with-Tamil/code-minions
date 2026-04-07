# CodeMinions — API Reference

> These docs define the full public contract of the SDK.
> Implementation must match these exactly.
> If an example in `examples/` cannot be expressed cleanly, a contract here is wrong.

## Public API surface

```python
from codeminions import (
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

from codeminions.tools import mcp_tools
from codeminions.testing import MockModel, MockEnvironment, run_blueprint_test
```

## Documents

| # | File | What it defines |
|---|------|----------------|
| 01 | `01_task.md` | `Task` — structured run input |
| 02 | `02_tool.md` | `@tool`, tool contract, output policy, MCP tools |
| 03 | `03_context.md` | `RunContext`, `ExecResult`, `RunConfig` |
| 04 | `04_nodes.md` | `DeterministicNode`, `AgentNode`, `JudgeNode`, `ParallelNode`, `LoopNode`, `condition` |
| 05 | `05_blueprint.md` | `Blueprint`, state, execution model, composition, validation |
| 06 | `06_environments.md` | `DockerEnv`, `GitWorktreeEnv`, `LocalEnv`, `BaseEnvironment` protocol |
| 07 | `07_models.md` | `ClaudeModel`, `OpenAIModel`, `BaseModelProtocol` |
| 08 | `08_minion.md` | `Minion` runner, run methods, event hooks, config |
| 09 | `09_result.md` | `RunResult`, `EscalationResult`, `Trace`, test assertions |
| 10 | `10_testing.md` | `MockModel`, `MockEnvironment`, `run_blueprint_test` |

## Dependency order (for implementation)

```
Task
↓
Tool + RunContext
↓
DeterministicNode + AgentNode + JudgeNode + ParallelNode + LoopNode
↓
Blueprint + BlueprintEngine (internal)
↓
LocalEnv → GitWorktreeEnv → DockerEnv
↓
ClaudeModel → OpenAIModel
↓
Minion (ties everything)
↓
RunResult + EscalationResult
↓
MockModel + MockEnvironment + run_blueprint_test
```
