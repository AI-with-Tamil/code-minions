"""CodeMinions — Python SDK for building unattended agentic coding harnesses."""

__version__ = "0.1.0"

# Core
from codeminions.core.blueprint import Blueprint, BlueprintValidationError
from codeminions.core.context import ExecResult, RunConfig, RunContext
from codeminions.core.minion import ConfigurationError, Minion
from codeminions.core.node import (
    AgentNode,
    AnyNode,
    DeterministicNode,
    JudgeNode,
    LoopNode,
    ParallelNode,
)
from codeminions.core.result import EscalationResult, RunResult
from codeminions.core.task import Task
from codeminions.core.tool import Tool, ToolDefinitionError, ToolOutputPolicy, ToolResult, tool

# Models
from codeminions.models.claude import ClaudeModel
from codeminions.models.openai import OpenAIModel

# Environments
from codeminions.environments.docker import DockerEnv
from codeminions.environments.local import LocalEnv
from codeminions.environments.worktree import GitWorktreeEnv

# Tool subsets
from codeminions.tools import CI_TOOLS, CODE_TOOLS, PROGRESS_TOOLS, SHELL_TOOLS, WEB_TOOLS

# Built-in blueprints
from codeminions.blueprints.coding import coding_blueprint

# Events
from codeminions.events import MinionEvent

__all__ = [
    # Core
    "Minion",
    "Blueprint",
    "BlueprintValidationError",
    "Task",
    "AgentNode",
    "DeterministicNode",
    "JudgeNode",
    "ParallelNode",
    "LoopNode",
    "AnyNode",
    "tool",
    "Tool",
    "ToolResult",
    "ToolOutputPolicy",
    "ToolDefinitionError",
    "RunContext",
    "RunConfig",
    "ExecResult",
    "RunResult",
    "EscalationResult",
    "ConfigurationError",
    # Models
    "ClaudeModel",
    "OpenAIModel",
    # Environments
    "DockerEnv",
    "GitWorktreeEnv",
    "LocalEnv",
    # Tool subsets
    "CODE_TOOLS",
    "SHELL_TOOLS",
    "CI_TOOLS",
    "WEB_TOOLS",
    "PROGRESS_TOOLS",
    # Built-in blueprints
    "coding_blueprint",
    # Events
    "MinionEvent",
    # Version
    "__version__",
]
