"""Built-in tool subsets."""

from minion.tools.code import edit_file, glob, grep, read_file, write_file
from minion.tools.shell import (
    git_add,
    git_commit,
    git_diff,
    git_log,
    git_status,
    run_command,
)
from minion.tools.ci import get_test_output, run_linter, run_tests
from minion.tools.mcp import (
    MCPClient,
    MCPConfigurationError,
    MCPProtocolError,
    MCPServerConfig,
    MCPTransportError,
    complete_mcp_prompt,
    complete_mcp_resource_template,
    get_mcp_prompt,
    get_mcp_display_name,
    list_mcp_prompts,
    list_mcp_resource_templates,
    list_mcp_resources,
    mcp_tools,
    read_mcp_resource,
    register_mcp_server,
    subscribe_mcp_resource,
    unsubscribe_mcp_resource,
)

CODE_TOOLS = [read_file, write_file, edit_file, grep, glob]
SHELL_TOOLS = [run_command, git_diff, git_log, git_status, git_add, git_commit]
CI_TOOLS = [run_tests, run_linter, get_test_output]

__all__ = [
    "CODE_TOOLS",
    "SHELL_TOOLS",
    "CI_TOOLS",
    "mcp_tools",
    "MCPClient",
    "MCPServerConfig",
    "MCPConfigurationError",
    "MCPTransportError",
    "MCPProtocolError",
    "register_mcp_server",
    "list_mcp_resources",
    "list_mcp_resource_templates",
    "read_mcp_resource",
    "subscribe_mcp_resource",
    "unsubscribe_mcp_resource",
    "list_mcp_prompts",
    "get_mcp_prompt",
    "complete_mcp_prompt",
    "complete_mcp_resource_template",
    "get_mcp_display_name",
    "read_file",
    "write_file",
    "edit_file",
    "grep",
    "glob",
    "run_command",
    "git_diff",
    "git_log",
    "git_status",
    "git_add",
    "git_commit",
    "run_tests",
    "run_linter",
    "get_test_output",
]
