"""Minion SDK — Python SDK for building unattended agentic coding harnesses."""

# Core
from minion.core.blueprint import Blueprint, BlueprintValidationError
from minion.core.context import ExecResult, RunConfig, RunContext
from minion.core.minion import ConfigurationError, Minion
from minion.core.node import (
    AgentNode,
    AnyNode,
    DeterministicNode,
    JudgeNode,
    LoopNode,
    ParallelNode,
)
from minion.core.result import EscalationResult, RunResult
from minion.core.task import Task
from minion.core.tool import Tool, ToolDefinitionError, ToolOutputPolicy, ToolResult, tool

# Models
from minion.models.claude import ClaudeModel
from minion.models.openai import OpenAIModel

# Environments
from minion.environments.docker import DockerEnv
from minion.environments.local import LocalEnv
from minion.environments.worktree import GitWorktreeEnv

# Tool subsets
from minion.tools import CI_TOOLS, CODE_TOOLS, SHELL_TOOLS

# Built-in blueprints
from minion.blueprints.coding import coding_blueprint

# Events
from minion.events import MinionEvent

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
    # Built-in blueprints
    "coding_blueprint",
    # Events
    "MinionEvent",
]
