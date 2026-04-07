"""Tests for built-in tools: list_dir, web_fetch, web_search, diff_history, write_todos."""

import pytest

from minion.testing import MockEnvironment, MockModel
from minion.tools.code import list_dir
from minion.tools.shell import diff_history
from minion.tools.web import web_fetch, web_search, _strip_html
from minion.tools.progress import write_todos, get_todos
from pydantic import BaseModel


# --- Helpers ---

class ToolState(BaseModel):
    output: str = ""


def _make_ctx(env=None, state=None):
    """Build a minimal RunContext for direct tool testing."""
    from minion.core.context import RunConfig, RunContext
    from minion.core.task import Task
    from minion.trace import Trace

    return RunContext(
        env=env or MockEnvironment(),
        state=state or ToolState(),
        trace=Trace(run_id="test"),
        model=MockModel(),
        config=RunConfig(),
        task=Task(description="test"),
        run_id="test",
        node="test",
    )


# --- list_dir ---

class TestListDir:
    @pytest.mark.asyncio
    async def test_lists_directory(self):
        env = MockEnvironment(exec_results={
            "find . -maxdepth 1 -not -path '*/\\.*' | sort":
                ".\n./src\n./tests\n./README.md\n",
        })
        ctx = _make_ctx(env=env)
        result = await list_dir.execute(ctx)
        assert "src" in result.content
        assert "tests" in result.content
        assert "README.md" in result.content

    @pytest.mark.asyncio
    async def test_clamps_depth(self):
        env = MockEnvironment(exec_results={
            "find . -maxdepth 3 -not -path '*/\\.*' | sort": ".\n",
        })
        ctx = _make_ctx(env=env)
        result = await list_dir.execute(ctx, max_depth=99)
        assert result.content is not None

    @pytest.mark.asyncio
    async def test_custom_path(self):
        env = MockEnvironment(exec_results={
            "find src -maxdepth 2 -not -path '*/\\.*' | sort":
                "src\nsrc/minion\nsrc/minion/__init__.py\n",
        })
        ctx = _make_ctx(env=env)
        result = await list_dir.execute(ctx, path="src", max_depth=2)
        assert "minion" in result.content


# --- web_fetch ---

class TestWebFetch:
    @pytest.mark.asyncio
    async def test_fetches_plain_text(self):
        env = MockEnvironment(exec_results={
            "curl -sL --max-time 15 --max-filesize 2097152 "
            "-H 'User-Agent: Minion-SDK/0.1' "
            "'https://example.com/api'": "Hello world",
        })
        ctx = _make_ctx(env=env)
        result = await web_fetch.execute(ctx, url="https://example.com/api")
        assert result.content == "Hello world"

    @pytest.mark.asyncio
    async def test_strips_html(self):
        html_content = "<html><body><h1>Title</h1><p>Content</p></body></html>"
        env = MockEnvironment(exec_results={
            "curl -sL --max-time 15 --max-filesize 2097152 "
            "-H 'User-Agent: Minion-SDK/0.1' "
            "'https://example.com'": html_content,
        })
        ctx = _make_ctx(env=env)
        result = await web_fetch.execute(ctx, url="https://example.com")
        assert "Title" in result.content
        assert "Content" in result.content
        assert "<html>" not in result.content

    @pytest.mark.asyncio
    async def test_handles_fetch_failure(self):
        env = MockEnvironment(exec_results={
            "curl -sL --max-time 15 --max-filesize 2097152 "
            "-H 'User-Agent: Minion-SDK/0.1' "
            "'https://fail.example.com'": 7,  # curl exit code 7 = connection refused
        })
        ctx = _make_ctx(env=env)
        result = await web_fetch.execute(ctx, url="https://fail.example.com")
        assert "fetch failed" in result.content


class TestStripHtml:
    def test_removes_tags(self):
        assert "hello" in _strip_html("<b>hello</b>")
        assert "<b>" not in _strip_html("<b>hello</b>")

    def test_removes_script_blocks(self):
        html = "<script>alert('xss')</script><p>safe</p>"
        text = _strip_html(html)
        assert "alert" not in text
        assert "safe" in text

    def test_decodes_entities(self):
        assert "&" in _strip_html("&amp;")

    def test_respects_max_chars(self):
        result = _strip_html("<p>" + "x" * 1000 + "</p>", max_chars=50)
        assert len(result) <= 50


# --- web_search ---

class TestWebSearch:
    @pytest.mark.asyncio
    async def test_uses_ddgr_when_available(self):
        env = MockEnvironment(exec_results={
            "command -v ddgr": "/usr/local/bin/ddgr",
            "ddgr --json -n 5 'python async' 2>/dev/null":
                '[{"title": "Asyncio docs", "url": "https://docs.python.org"}]',
        })
        ctx = _make_ctx(env=env)
        result = await web_search.execute(ctx, query="python async")
        assert "Asyncio docs" in result.content

    @pytest.mark.asyncio
    async def test_fallback_message_when_no_cli(self):
        env = MockEnvironment(exec_results={
            "command -v ddgr": 1,
            "command -v googler": 1,
            "curl -sL --max-time 10 *": 1,
        })
        ctx = _make_ctx(env=env)
        result = await web_search.execute(ctx, query="test query")
        assert "unavailable" in result.content or "mcp_tools" in result.content


# --- diff_history ---

class TestDiffHistory:
    @pytest.mark.asyncio
    async def test_shows_changed_files(self):
        env = MockEnvironment(exec_results={
            "git status --short": " M src/app.py\n?? new_file.py\n",
            "git diff --stat HEAD 2>/dev/null || git diff --stat":
                " src/app.py | 3 ++-\n 1 file changed, 2 insertions(+), 1 deletion(-)\n",
        })
        ctx = _make_ctx(env=env)
        result = await diff_history.execute(ctx)
        assert "src/app.py" in result.content
        assert "new_file.py" in result.content

    @pytest.mark.asyncio
    async def test_no_changes(self):
        env = MockEnvironment(exec_results={
            "git status --short": "",
            "git diff --stat HEAD 2>/dev/null || git diff --stat": "",
        })
        ctx = _make_ctx(env=env)
        result = await diff_history.execute(ctx)
        assert "no changes" in result.content


# --- write_todos / get_todos ---

class TestProgressTools:
    @pytest.mark.asyncio
    async def test_write_and_get(self):
        ctx = _make_ctx()
        result = await write_todos.execute(ctx, todos=[
            {"id": "1", "description": "Read codebase", "status": "completed"},
            {"id": "2", "description": "Implement feature", "status": "in_progress"},
            {"id": "3", "description": "Write tests", "status": "pending"},
        ])
        assert "3 items" in result.content
        assert "1 done" in result.content

        get_result = await get_todos.execute(ctx)
        assert "[x] 1: Read codebase" in get_result.content
        assert "[>] 2: Implement feature" in get_result.content
        assert "[ ] 3: Write tests" in get_result.content

    @pytest.mark.asyncio
    async def test_empty_todos(self):
        ctx = _make_ctx()
        result = await get_todos.execute(ctx)
        assert "no todos" in result.content

    @pytest.mark.asyncio
    async def test_invalid_status_defaults_to_pending(self):
        ctx = _make_ctx()
        await write_todos.execute(ctx, todos=[
            {"id": "1", "description": "task", "status": "bogus"},
        ])
        result = await get_todos.execute(ctx)
        assert "[ ] 1: task" in result.content

    @pytest.mark.asyncio
    async def test_updates_replace_previous(self):
        ctx = _make_ctx()
        await write_todos.execute(ctx, todos=[
            {"id": "1", "description": "old task"},
        ])
        await write_todos.execute(ctx, todos=[
            {"id": "1", "description": "new task", "status": "completed"},
        ])
        result = await get_todos.execute(ctx)
        assert "new task" in result.content
        assert "old task" not in result.content


# --- Tool subsets include new tools ---

class TestToolSubsets:
    def test_code_tools_includes_list_dir(self):
        from minion.tools import CODE_TOOLS
        names = [t.name for t in CODE_TOOLS]
        assert "list_dir" in names

    def test_shell_tools_includes_diff_history(self):
        from minion.tools import SHELL_TOOLS
        names = [t.name for t in SHELL_TOOLS]
        assert "diff_history" in names

    def test_web_tools_exists(self):
        from minion.tools import WEB_TOOLS
        names = [t.name for t in WEB_TOOLS]
        assert "web_fetch" in names
        assert "web_search" in names

    def test_progress_tools_exists(self):
        from minion.tools import PROGRESS_TOOLS
        names = [t.name for t in PROGRESS_TOOLS]
        assert "write_todos" in names
        assert "get_todos" in names

    def test_public_api_exports(self):
        from minion import WEB_TOOLS, PROGRESS_TOOLS
        assert len(WEB_TOOLS) == 2
        assert len(PROGRESS_TOOLS) == 2
