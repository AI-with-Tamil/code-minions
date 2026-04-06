"""Errors for Minion's MCP client integration."""

from __future__ import annotations


class MCPError(RuntimeError):
    """Base error for MCP integration failures."""


class MCPConfigurationError(MCPError, ValueError):
    """Raised when an MCP server configuration is missing or invalid."""


class MCPTransportError(MCPError):
    """Raised when an MCP transport cannot be opened or maintained."""


class MCPProtocolError(MCPError):
    """Raised when the server returns an invalid or error MCP payload."""


class MCPAuthError(MCPError):
    """Raised when authentication is required or rejected."""
