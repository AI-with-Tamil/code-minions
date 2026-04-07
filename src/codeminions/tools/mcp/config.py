"""Configuration and resolution for MCP servers."""

from __future__ import annotations

import json
import os
import re
import shlex
from dataclasses import dataclass, field
from typing import Any, Literal

from codeminions.tools.mcp.errors import MCPConfigurationError
from codeminions.tools.mcp.registry import get_registered_mcp_server, has_registered_mcp_server


Transport = Literal["stdio", "streamable_http", "sse"]


@dataclass(frozen=True)
class MCPServerConfig:
    """Resolved MCP server connection settings."""

    transport: Transport = "stdio"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] | None = None
    cwd: str | None = None
    url: str | None = None
    headers: dict[str, str] | None = None
    timeout_seconds: float = 5.0
    sse_read_timeout: float = 300.0
    read_timeout_seconds: float | None = None
    terminate_on_close: bool = True
    roots: list[str] = field(default_factory=list)
    title_prefix: str | None = None
    http_auth: Any | None = None
    sampling_callback: Any | None = None
    elicitation_callback: Any | None = None
    logging_callback: Any | None = None
    message_handler: Any | None = None


def resolve_mcp_server_config(
    *,
    server: str | MCPServerConfig,
    transport: Transport | None = None,
    command: str | None = None,
    args: list[str] | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
    url: str | None = None,
    headers: dict[str, str] | None = None,
    timeout_seconds: float | None = None,
    sse_read_timeout: float | None = None,
    read_timeout_seconds: float | None = None,
    terminate_on_close: bool | None = None,
    roots: list[str] | None = None,
    http_auth: Any | None = None,
    sampling_callback: Any | None = None,
    elicitation_callback: Any | None = None,
    logging_callback: Any | None = None,
    message_handler: Any | None = None,
) -> MCPServerConfig:
    base = server if isinstance(server, MCPServerConfig) else _config_from_name(server)
    resolved = MCPServerConfig(
        transport=transport or base.transport,
        command=command if command is not None else base.command,
        args=list(args) if args is not None else list(base.args),
        env=env if env is not None else (dict(base.env) if base.env is not None else None),
        cwd=cwd if cwd is not None else base.cwd,
        url=url if url is not None else base.url,
        headers=headers if headers is not None else (dict(base.headers) if base.headers is not None else None),
        timeout_seconds=timeout_seconds if timeout_seconds is not None else base.timeout_seconds,
        sse_read_timeout=sse_read_timeout if sse_read_timeout is not None else base.sse_read_timeout,
        read_timeout_seconds=read_timeout_seconds if read_timeout_seconds is not None else base.read_timeout_seconds,
        terminate_on_close=terminate_on_close if terminate_on_close is not None else base.terminate_on_close,
        roots=list(roots) if roots is not None else list(base.roots),
        title_prefix=base.title_prefix,
        http_auth=http_auth if http_auth is not None else base.http_auth,
        sampling_callback=sampling_callback if sampling_callback is not None else base.sampling_callback,
        elicitation_callback=elicitation_callback if elicitation_callback is not None else base.elicitation_callback,
        logging_callback=logging_callback if logging_callback is not None else base.logging_callback,
        message_handler=message_handler if message_handler is not None else base.message_handler,
    )
    validate_mcp_server_config(resolved)
    return resolved


def validate_mcp_server_config(config: MCPServerConfig) -> None:
    if config.transport == "stdio":
        if not config.command:
            raise MCPConfigurationError("stdio MCP servers require a command")
    elif config.transport in {"streamable_http", "sse"}:
        if not config.url:
            raise MCPConfigurationError(f"{config.transport} MCP servers require a url")
    else:
        raise MCPConfigurationError(f"Unsupported MCP transport: {config.transport}")


def _config_from_name(name: str) -> MCPServerConfig:
    if has_registered_mcp_server(name):
        config = get_registered_mcp_server(name)
        if not isinstance(config, MCPServerConfig):
            raise MCPConfigurationError(f"Registered MCP server '{name}' is not an MCPServerConfig")
        return config

    prefix = _env_prefix(name)
    transport = _env(prefix, "TRANSPORT")
    command = _env(prefix, "COMMAND")
    args = _env_json_or_shlex(prefix, "ARGS")
    env = _env_json_dict(prefix, "ENV")
    cwd = _env(prefix, "CWD")
    url = _env(prefix, "URL")
    headers = _env_json_dict(prefix, "HEADERS")
    timeout_seconds = _env_float(prefix, "TIMEOUT_SECONDS")
    sse_read_timeout = _env_float(prefix, "SSE_READ_TIMEOUT")
    read_timeout_seconds = _env_float(prefix, "READ_TIMEOUT_SECONDS")
    terminate_on_close = _env_bool(prefix, "TERMINATE_ON_CLOSE")
    roots = _env_json_or_shlex(prefix, "ROOTS")

    config = MCPServerConfig(
        transport=(transport or ("streamable_http" if url else "stdio")),  # type: ignore[arg-type]
        command=command,
        args=args,
        env=env,
        cwd=cwd,
        url=url,
        headers=headers,
        timeout_seconds=timeout_seconds if timeout_seconds is not None else 5.0,
        sse_read_timeout=sse_read_timeout if sse_read_timeout is not None else 300.0,
        read_timeout_seconds=read_timeout_seconds,
        terminate_on_close=terminate_on_close if terminate_on_close is not None else True,
        roots=roots,
        title_prefix=name,
    )

    if not any([transport, command, args, env, cwd, url, headers, roots]):
        raise MCPConfigurationError(
            f"No MCP configuration found for server '{name}'. "
            f"Register it with register_mcp_server(), pass an MCPServerConfig(), "
            f"or set environment variables like {prefix}_COMMAND / {prefix}_URL."
        )

    return config


def _env_prefix(name: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return f"CODEMINIONS_MCP_{normalized}"


def _env(prefix: str, key: str) -> str | None:
    return os.environ.get(f"{prefix}_{key}")


def _env_bool(prefix: str, key: str) -> bool | None:
    value = _env(prefix, key)
    if value is None:
        return None
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(prefix: str, key: str) -> float | None:
    value = _env(prefix, key)
    if value is None:
        return None
    return float(value)


def _env_json_dict(prefix: str, key: str) -> dict[str, str] | None:
    value = _env(prefix, key)
    if value is None:
        return None
    parsed = json.loads(value)
    if not isinstance(parsed, dict):
        raise MCPConfigurationError(f"{prefix}_{key} must be a JSON object")
    return {str(k): str(v) for k, v in parsed.items()}


def _env_json_or_shlex(prefix: str, key: str) -> list[str]:
    value = _env(prefix, key)
    if value is None or value.strip() == "":
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return shlex.split(value)
    if not isinstance(parsed, list):
        raise MCPConfigurationError(f"{prefix}_{key} must be a JSON array or shell words")
    return [str(item) for item in parsed]
