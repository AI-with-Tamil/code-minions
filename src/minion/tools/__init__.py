"""Built-in tool subsets."""

from minion.tools.code import edit_file, glob, grep, list_dir, read_file, write_file
from minion.tools.shell import (
    diff_history,
    git_add,
    git_commit,
    git_diff,
    git_log,
    git_status,
    run_command,
)
from minion.tools.ci import get_test_output, run_linter, run_tests
from minion.tools.web import web_fetch, web_search
from minion.tools.progress import get_todos, write_todos
from minion.tools.mcp import (
    InMemoryTokenStorage,
    MCPClient,
    MCPConfigurationError,
    MCPProtocolError,
    MCPServerConfig,
    MCPTransportError,
    build_oauth_client_metadata,
    complete_mcp_prompt,
    complete_mcp_resource_template,
    create_oauth_provider,
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

CODE_TOOLS = [read_file, write_file, edit_file, grep, glob, list_dir]
SHELL_TOOLS = [run_command, git_diff, git_log, git_status, git_add, git_commit, diff_history]
CI_TOOLS = [run_tests, run_linter, get_test_output]
WEB_TOOLS = [web_fetch, web_search]
PROGRESS_TOOLS = [write_todos, get_todos]

__all__ = [
    "CODE_TOOLS",
    "SHELL_TOOLS",
    "CI_TOOLS",
    "WEB_TOOLS",
    "PROGRESS_TOOLS",
    # Code tools
    "read_file",
    "write_file",
    "edit_file",
    "grep",
    "glob",
    "list_dir",
    # Shell tools
    "run_command",
    "git_diff",
    "git_log",
    "git_status",
    "git_add",
    "git_commit",
    "diff_history",
    # CI tools
    "run_tests",
    "run_linter",
    "get_test_output",
    # Web tools
    "web_fetch",
    "web_search",
    # Progress tools
    "write_todos",
    "get_todos",
    # MCP
    "mcp_tools",
    "MCPClient",
    "InMemoryTokenStorage",
    "MCPServerConfig",
    "MCPConfigurationError",
    "MCPTransportError",
    "MCPProtocolError",
    "create_oauth_provider",
    "build_oauth_client_metadata",
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
]
