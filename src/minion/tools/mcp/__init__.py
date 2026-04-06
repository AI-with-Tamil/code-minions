"""Package-level MCP client support for Minion."""

from minion.tools.mcp.client import MCPClient
from minion.tools.mcp.compat import mcp_sdk_version
from minion.tools.mcp.config import MCPServerConfig, Transport, resolve_mcp_server_config
from minion.tools.mcp.errors import (
    MCPAuthError,
    MCPConfigurationError,
    MCPError,
    MCPProtocolError,
    MCPTransportError,
)
from minion.tools.mcp.prompts import get_mcp_prompt, list_mcp_prompts
from minion.tools.mcp.registry import register_mcp_server
from minion.tools.mcp.resources import list_mcp_resources, read_mcp_resource
from minion.tools.mcp.tools import mcp_tools

__all__ = [
    "MCPClient",
    "MCPServerConfig",
    "Transport",
    "MCPError",
    "MCPConfigurationError",
    "MCPTransportError",
    "MCPProtocolError",
    "MCPAuthError",
    "resolve_mcp_server_config",
    "register_mcp_server",
    "mcp_tools",
    "list_mcp_resources",
    "read_mcp_resource",
    "list_mcp_prompts",
    "get_mcp_prompt",
    "mcp_sdk_version",
]
