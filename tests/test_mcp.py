"""Integration tests for MCP tool, resource, and prompt support."""

from __future__ import annotations

import json
import importlib.util
import os
import socket
import subprocess
import sys
import time

import pytest
from pydantic import BaseModel

from codeminions import RunConfig, RunContext, Task
from codeminions.testing import MockEnvironment, MockModel
from codeminions.tools import (
    InMemoryTokenStorage,
    MCPClient,
    MCPServerConfig,
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
)
from codeminions.trace import Trace

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None,
    reason="optional 'mcp' dependency is not installed",
)


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

@mcp.resource("greeting://{name}")
def dynamic_greeting(name: str) -> str:
    return f"hello {name}"

@mcp.prompt()
def review_code(code: str, style: str = "friendly") -> str:
    return f"Review this code in {style} style: {code}"

@mcp.completion()
async def complete(ref, argument, context):
    uri = getattr(ref, "uri", "")
    name = getattr(ref, "name", "")
    if uri == "greeting://{name}" and argument.name == "name":
        prefix = argument.value.lower()
        values = [value for value in ["Alice", "Alicia", "Bob"] if value.lower().startswith(prefix)]
        return {"values": values}
    if name == "review_code" and argument.name == "style":
        prefix = argument.value.lower()
        values = [value for value in ["friendly", "formal", "casual"] if value.startswith(prefix)]
        return {"values": values}
    return {"values": []}

if __name__ == "__main__":
    mcp.run("stdio")
""".strip()
    )
    return str(server_file)


def _write_streamable_http_server(tmp_path) -> str:
    server_file = tmp_path / "mcp_http_server.py"
    server_file.write_text(
        """
import os
import uvicorn
from mcp.server.fastmcp import FastMCP

port = int(os.environ["CODEMINIONS_TEST_MCP_PORT"])
mcp = FastMCP("http-test-server", host="127.0.0.1", port=port)

@mcp.tool()
def echo(value: str) -> str:
    return f"http:{value}"

@mcp.resource("memo://http")
def http_resource() -> str:
    return "hello from http resource"

@mcp.prompt()
def explain(topic: str) -> str:
    return f"Explain {topic}"

app = mcp.streamable_http_app()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
""".strip()
    )
    return str(server_file)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_http_server(url: str, timeout_seconds: float = 10.0) -> None:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 80
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Timed out waiting for MCP HTTP server at {url}")


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
    assert {str(resource.uri) for resource in resources} == {"memo://greeting"}

    templates = list_mcp_resource_templates(config)
    assert [template.uriTemplate for template in templates] == ["greeting://{name}"]
    assert get_mcp_display_name(templates[0]) == "dynamic_greeting"

    resource_text = read_mcp_resource(config, "memo://greeting")
    assert resource_text == "hello from resource"

    prompts = list_mcp_prompts(config)
    assert len(prompts) == 1
    assert prompts[0].name == "review_code"
    assert get_mcp_display_name(prompts[0]) == "review_code"

    prompt_text = get_mcp_prompt(config, "review_code", {"code": "print('hi')", "style": "formal"})
    assert "Review this code in formal style: print('hi')" in prompt_text

    prompt_completions = complete_mcp_prompt(
        config,
        name="review_code",
        argument_name="style",
        argument_value="f",
    )
    assert prompt_completions == ["friendly", "formal"]

    template_completions = complete_mcp_resource_template(
        config,
        uri_template="greeting://{name}",
        argument_name="name",
        argument_value="Al",
    )
    assert template_completions == ["Alice", "Alicia"]


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
        templates = await client.list_resource_templates()
        prompts = await client.list_prompts()
        prompt_completion = await client.complete_prompt(
            name="review_code",
            argument_name="style",
            argument_value="c",
        )
        template_completion = await client.complete_resource_template(
            uri_template="greeting://{name}",
            argument_name="name",
            argument_value="B",
        )
        ping_result = await client.send_ping()

        assert {tool.name for tool in tools} == {"echo", "add"}
        assert [str(resource.uri) for resource in resources] == ["memo://greeting"]
        assert [template.uriTemplate for template in templates] == ["greeting://{name}"]
        assert [prompt.name for prompt in prompts] == ["review_code"]
        assert prompt_completion.completion.values == ["casual"]
        assert template_completion.completion.values == ["Bob"]
        assert ping_result is not None


def test_mcp_tools_resolve_named_server_from_env(tmp_path, monkeypatch):
    server_script = _write_stdio_server(tmp_path)
    monkeypatch.setenv("CODEMINIONS_MCP_TEST_SERVER_COMMAND", sys.executable)
    monkeypatch.setenv("CODEMINIONS_MCP_TEST_SERVER_ARGS", json.dumps([server_script]))

    tools = mcp_tools("test-server", tools=["echo"])
    assert [tool.name for tool in tools] == ["echo"]


def test_oauth_helper_builders():
    metadata = build_oauth_client_metadata(
        redirect_uris=["http://localhost:3000/callback"],
        scope="user",
        client_name="Minion Test Client",
    )
    storage = InMemoryTokenStorage()
    provider = create_oauth_provider(
        server_url="https://auth.example.com",
        client_metadata=metadata,
        storage=storage,
        redirect_handler=lambda url: _noop_redirect(url),
        callback_handler=_noop_callback,
    )

    assert metadata.client_name == "Minion Test Client"
    assert storage.tokens is None
    assert provider is not None


async def _noop_redirect(url: str) -> None:
    return None


async def _noop_callback() -> tuple[str, str | None]:
    return ("code", None)


@pytest.mark.asyncio
async def test_streamable_http_mcp_client_round_trip(tmp_path):
    server_script = _write_streamable_http_server(tmp_path)
    port = _free_port()
    env = dict(os.environ)
    env["CODEMINIONS_TEST_MCP_PORT"] = str(port)
    proc = subprocess.Popen(
        [sys.executable, server_script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        _wait_for_http_server(f"http://127.0.0.1:{port}/mcp")
        async with MCPClient(
            MCPServerConfig(
                transport="streamable_http",
                url=f"http://127.0.0.1:{port}/mcp",
            )
        ) as client:
            assert client.initialization.protocol_version is not None
            tools = await client.list_tools()
            resources = await client.list_resources()
            prompts = await client.list_prompts()
            tool_result = await client.call_tool("echo", {"value": "hello"})

            assert {tool.name for tool in tools} == {"echo"}
            assert [str(resource.uri) for resource in resources] == ["memo://http"]
            assert [prompt.name for prompt in prompts] == ["explain"]
            assert "http:hello" in (tool_result.content[0].text if tool_result.content else "")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
