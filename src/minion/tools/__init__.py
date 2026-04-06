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
from minion.tools.mcp import mcp_tools

CODE_TOOLS = [read_file, write_file, edit_file, grep, glob]
SHELL_TOOLS = [run_command, git_diff, git_log, git_status, git_add, git_commit]
CI_TOOLS = [run_tests, run_linter, get_test_output]

__all__ = [
    "CODE_TOOLS",
    "SHELL_TOOLS",
    "CI_TOOLS",
    "mcp_tools",
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
