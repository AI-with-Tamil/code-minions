"""Built-in tool subsets."""

from minion.tools.code import (
    append_file,
    edit_file,
    file_exists,
    glob,
    grep,
    insert_after,
    insert_before,
    list_dir,
    read_file,
    replace_regex,
    write_file,
)
from minion.tools.shell import (
    diff_history,
    git_add,
    git_commit,
    git_create_branch,
    git_checkout,
    git_diff,
    git_log,
    git_push,
    git_show,
    git_status,
    pwd,
    run_command,
)
from minion.tools.ci import (
    get_test_output,
    run_linter,
    run_tests,
    summarize_failure_output,
)
from minion.tools.search import find_files, search_files
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

CODE_TOOLS = [
    read_file, write_file, edit_file, append_file,
    insert_before, insert_after, replace_regex,
    file_exists, grep, glob, list_dir,
]
SHELL_TOOLS = [
    run_command, pwd,
    git_diff, git_log, git_status, git_show,
    git_add, git_commit, git_create_branch, git_checkout, git_push,
    diff_history,
]
CI_TOOLS = [run_tests, run_linter, get_test_output, summarize_failure_output]
SEARCH_TOOLS = [find_files, search_files]
WEB_TOOLS = [web_fetch, web_search]
PROGRESS_TOOLS = [write_todos, get_todos]

__all__ = [
    "CODE_TOOLS",
    "SHELL_TOOLS",
    "CI_TOOLS",
    "SEARCH_TOOLS",
    "WEB_TOOLS",
    "PROGRESS_TOOLS",
    # Code tools
    "read_file",
    "write_file",
    "edit_file",
    "append_file",
    "insert_before",
    "insert_after",
    "replace_regex",
    "file_exists",
    "grep",
    "glob",
    "list_dir",
    # Shell tools
    "run_command",
    "pwd",
    "git_diff",
    "git_log",
    "git_status",
    "git_show",
    "git_add",
    "git_commit",
    "git_create_branch",
    "git_checkout",
    "git_push",
    "diff_history",
    # CI tools
    "run_tests",
    "run_linter",
    "get_test_output",
    "summarize_failure_output",
    # Search tools
    "find_files",
    "search_files",
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
