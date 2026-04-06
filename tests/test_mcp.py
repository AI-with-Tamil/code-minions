"""Integration tests for MCP tool, resource, and prompt support."""

from __future__ import annotations

import json
import sys

import pytest
from pydantic import BaseModel

from minion import RunConfig, RunContext, Task
from minion.testing import MockEnvironment, MockModel
from minion.tools import (
    MCPClient,
    MCPServerConfig,
    get_mcp_prompt,
    list_mcp_prompts,
    list_mcp_resources,
    mcp_tools,
    read_mcp_resource,
)
from minion.trace import Trace


class _State(BaseModel):
    branch: str = ""


def _build_ctx() -> RunContext:
    return RunContext(
        env=MockEnvironment(),
        state=_State(),
        trace=Trace(run_id="run-1"),
        model=MockModel(),
        config=RunConfig(),
        task=Task(description="Use MCP"),
        run_id="run-1",
        node="implement",
    )


def _write_stdio_server(tmp_path) -> str:
    server_file = tmp_path / "mcp_server.py"
    server_file.write_text(
        """
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test-server")

@mcp.tool()
def echo(value: str) -> str:
    return f"echo:{value}"

@mcp.tool()
def add(a: int, b: int) -> dict:
    return {"sum": a + b}

@mcp.resource("memo://greeting")
def greeting() -> str:
    return "hello from resource"

@mcp.prompt()
def review_code(code: str) -> str:
    return f"Review this code: {code}"

if __name__ == "__main__":
    mcp.run("stdio")
""".strip()
    )
    return str(server_file)


@pytest.mark.asyncio
async def test_mcp_tools_load_and_execute_stdio_server(tmp_path):
    server_script = _write_stdio_server(tmp_path)
    tools = mcp_tools(
        MCPServerConfig(
            transport="stdio",
            command=sys.executable,
            args=[server_script],
        )
    )

    names = {tool.name for tool in tools}
    assert names == {"echo", "add"}

    ctx = _build_ctx()

    echo_tool = next(tool for tool in tools if tool.name == "echo")
    echo_result = await echo_tool.execute(ctx, value="hello")
    assert echo_result.error is None
    assert echo_result.content == "echo:hello"

    add_tool = next(tool for tool in tools if tool.name == "add")
    add_result = await add_tool.execute(ctx, a=2, b=3)
    assert add_result.error is None
    assert json.loads(add_result.content or "{}")["sum"] == 5


def test_mcp_resources_and_prompts_stdio_server(tmp_path):
    server_script = _write_stdio_server(tmp_path)
    config = MCPServerConfig(
        transport="stdio",
        command=sys.executable,
        args=[server_script],
    )

    resources = list_mcp_resources(config)
    assert len(resources) == 1
    assert str(resources[0].uri) == "memo://greeting"

    resource_text = read_mcp_resource(config, "memo://greeting")
    assert resource_text == "hello from resource"

    prompts = list_mcp_prompts(config)
    assert len(prompts) == 1
    assert prompts[0].name == "review_code"

    prompt_text = get_mcp_prompt(config, "review_code", {"code": "print('hi')"})
    assert "Review this code: print('hi')" in prompt_text


@pytest.mark.asyncio
async def test_mcp_client_lists_tools_resources_and_prompts(tmp_path):
    server_script = _write_stdio_server(tmp_path)
    async with MCPClient(
        MCPServerConfig(
            transport="stdio",
            command=sys.executable,
            args=[server_script],
        )
    ) as client:
        tools = await client.list_tools()
        resources = await client.list_resources()
        prompts = await client.list_prompts()

        assert {tool.name for tool in tools} == {"echo", "add"}
        assert [str(resource.uri) for resource in resources] == ["memo://greeting"]
        assert [prompt.name for prompt in prompts] == ["review_code"]


def test_mcp_tools_resolve_named_server_from_env(tmp_path, monkeypatch):
    server_script = _write_stdio_server(tmp_path)
    monkeypatch.setenv("MINION_MCP_TEST_SERVER_COMMAND", sys.executable)
    monkeypatch.setenv("MINION_MCP_TEST_SERVER_ARGS", json.dumps([server_script]))

    tools = mcp_tools("test-server", tools=["echo"])
    assert [tool.name for tool in tools] == ["echo"]
