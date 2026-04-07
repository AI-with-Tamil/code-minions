"""Tests for built-in tools: code, search, shell, CI."""

import pytest

from codeminions.testing import MockEnvironment, MockModel
from codeminions.tools.code import (
    append_file, edit_file, file_exists, insert_after,
    insert_before, read_file, replace_regex,
)
from codeminions.tools.search import find_files, search_files
from codeminions.tools.shell import (
    git_checkout, git_create_branch, git_push,
    git_show, pwd,
)
from codeminions.tools.ci import summarize_failure_output
from pydantic import BaseModel


# --- Helpers ---

class ToolState(BaseModel):
    output: str = ""
    test_output: str = ""


def _make_ctx(env=None, state=None):
    """Build a minimal RunContext for direct tool testing."""
    from codeminions.core.context import RunConfig, RunContext
    from codeminions.core.task import Task
    from codeminions.trace import Trace

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


# ============================================================
#  Code tools — edit_file hardening
# ============================================================

class TestEditFile:
    @pytest.mark.asyncio
    async def test_successful_edit(self):
        env = MockEnvironment(
            files={"app.py": "def old():\n    pass\n"},
        )
        ctx = _make_ctx(env=env)
        result = await edit_file.execute(ctx, path="app.py", old="def old():\n    pass\n", new="def new():\n    return True\n")
        assert "Edited" in result.content
        assert "chars" in result.content

    @pytest.mark.asyncio
    async def test_old_text_not_found_single_line(self):
        env = MockEnvironment(
            files={"app.py": "def foo():\n    pass\n"},
        )
        ctx = _make_ctx(env=env)
        result = await edit_file.execute(ctx, path="app.py", old="def bar():", new="def baz():")
        assert result.error is not None
        assert "not found" in result.error
        assert "Hint" in result.error

    @pytest.mark.asyncio
    async def test_file_not_found(self):
        env = MockEnvironment(files={})
        ctx = _make_ctx(env=env)
        result = await edit_file.execute(ctx, path="missing.py", old="x", new="y")
        assert result.error is not None
        assert "File not found" in result.error


# ============================================================
#  Code tools — append_file
# ============================================================

class TestAppendFile:
    @pytest.mark.asyncio
    async def test_append_to_existing(self):
        env = MockEnvironment(files={"app.py": "line1\n"})
        ctx = _make_ctx(env=env)
        result = await append_file.execute(ctx, path="app.py", content="line2\n")
        assert "Appended" in result.content
        # Verify the file now has both lines
        read_result = await read_file.execute(ctx, path="app.py")
        assert "line1" in read_result.content
        assert "line2" in read_result.content

    @pytest.mark.asyncio
    async def test_append_creates_new_file(self):
        env = MockEnvironment(files={})
        ctx = _make_ctx(env=env)
        result = await append_file.execute(ctx, path="new.py", content="fresh content\n")
        assert "Created" in result.content
        read_result = await read_file.execute(ctx, path="new.py")
        assert "fresh content" in read_result.content


# ============================================================
#  Code tools — insert_before
# ============================================================

class TestInsertBefore:
    @pytest.mark.asyncio
    async def test_insert_before_match(self):
        env = MockEnvironment(files={"app.py": "def foo():\n    pass\n"})
        ctx = _make_ctx(env=env)
        result = await insert_before.execute(
            ctx, path="app.py", target="def foo():", content="# new function\n"
        )
        assert "Inserted" in result.content
        assert "before line 1" in result.content
        read_result = await read_file.execute(ctx, path="app.py")
        assert "# new function" in read_result.content
        assert "def foo():" in read_result.content

    @pytest.mark.asyncio
    async def test_target_not_found(self):
        env = MockEnvironment(files={"app.py": "def foo():\n    pass\n"})
        ctx = _make_ctx(env=env)
        result = await insert_before.execute(
            ctx, path="app.py", target="MISSING", content="# nope\n"
        )
        assert result.error is not None
        assert "not found" in result.error


# ============================================================
#  Code tools — insert_after
# ============================================================

class TestInsertAfter:
    @pytest.mark.asyncio
    async def test_insert_after_match(self):
        env = MockEnvironment(files={"app.py": "def foo():\n    pass\n"})
        ctx = _make_ctx(env=env)
        result = await insert_after.execute(
            ctx, path="app.py", target="def foo():", content="    return True\n"
        )
        assert "Inserted" in result.content
        assert "after line 1" in result.content
        read_result = await read_file.execute(ctx, path="app.py")
        assert "def foo():" in read_result.content
        assert "return True" in read_result.content


# ============================================================
#  Code tools — replace_regex
# ============================================================

class TestReplaceRegex:
    @pytest.mark.asyncio
    async def test_single_replacement(self):
        env = MockEnvironment(files={"app.py": "foo = 1\nfoo = 2\n"})
        ctx = _make_ctx(env=env)
        result = await replace_regex.execute(
            ctx, path="app.py", pattern=r"foo", replacement="bar"
        )
        assert "Replaced 1 occurrence" in result.content
        read_result = await read_file.execute(ctx, path="app.py")
        assert read_result.content.count("bar") == 1
        assert read_result.content.count("foo") == 1

    @pytest.mark.asyncio
    async def test_replace_all(self):
        env = MockEnvironment(files={"app.py": "foo = 1\nfoo = 2\n"})
        ctx = _make_ctx(env=env)
        result = await replace_regex.execute(
            ctx, path="app.py", pattern=r"foo", replacement="bar", replace_all=True
        )
        assert "Replaced 2 occurrence" in result.content
        read_result = await read_file.execute(ctx, path="app.py")
        assert "foo" not in read_result.content

    @pytest.mark.asyncio
    async def test_invalid_regex(self):
        env = MockEnvironment(files={"app.py": "data\n"})
        ctx = _make_ctx(env=env)
        result = await replace_regex.execute(
            ctx, path="app.py", pattern=r"[invalid", replacement="x"
        )
        assert result.error is not None
        assert "Invalid regex" in result.error

    @pytest.mark.asyncio
    async def test_no_match(self):
        env = MockEnvironment(files={"app.py": "hello\n"})
        ctx = _make_ctx(env=env)
        result = await replace_regex.execute(
            ctx, path="app.py", pattern=r"MISSING", replacement="x"
        )
        assert result.error is not None
        assert "matched 0" in result.error


# ============================================================
#  Code tools — file_exists
# ============================================================

class TestFileExists:
    @pytest.mark.asyncio
    async def test_file_exists_true(self):
        env = MockEnvironment(files={"app.py": "x = 1\n"})
        ctx = _make_ctx(env=env)
        result = await file_exists.execute(ctx, path="app.py")
        assert result.content == "true"

    @pytest.mark.asyncio
    async def test_file_exists_false(self):
        env = MockEnvironment(files={})
        ctx = _make_ctx(env=env)
        result = await file_exists.execute(ctx, path="missing.py")
        assert result.content == "false"


# ============================================================
#  Search tools — find_files
# ============================================================

class TestFindFiles:
    @pytest.mark.asyncio
    async def test_finds_by_extension(self):
        env = MockEnvironment(exec_results={
            "find . -not -path '*/.git/*' -not -name .git -not -path '*/.venv/*' -not -name .venv -not -path '*/node_modules/*' -not -name node_modules -not -path '*/__pycache__/*' -not -name __pycache__ -not -path '*/.worktrees/*' -not -name .worktrees -type f | sort":
                "./src/app.py\n./tests/test_app.py\n",
        })
        ctx = _make_ctx(env=env)
        result = await find_files.execute(ctx, extension=".py")
        assert "Found 2 file" in result.content
        assert "app.py" in result.content

    @pytest.mark.asyncio
    async def test_no_results(self):
        env = MockEnvironment(exec_results={
            "find . -not -path '*/.git/*' -not -name .git -not -path '*/.venv/*' -not -name .venv -not -path '*/node_modules/*' -not -name node_modules -not -path '*/__pycache__/*' -not -name __pycache__ -not -path '*/.worktrees/*' -not -name .worktrees -type f | sort":
                "",
        })
        ctx = _make_ctx(env=env)
        result = await find_files.execute(ctx, extension=".rs")
        assert "No files found" in result.content


# ============================================================
#  Search tools — search_files
# ============================================================

class TestSearchFiles:
    @pytest.mark.asyncio
    async def test_finds_files_containing_text(self):
        env = MockEnvironment(exec_results={
            "grep -r -li --include='*.py' 'def main' . 2>/dev/null | head -n 50 || true":
                "src/app.py\nsrc/cli.py\n",
        })
        ctx = _make_ctx(env=env)
        result = await search_files.execute(ctx, query="def main", file_pattern="*.py")
        assert "Found 2 file" in result.content
        assert "src/app.py" in result.content

    @pytest.mark.asyncio
    async def test_no_match(self):
        env = MockEnvironment(exec_results={
            "grep -r -li --include='*.py' NOTFOUND . 2>/dev/null | head -n 50 || true":
                "",
        })
        ctx = _make_ctx(env=env)
        result = await search_files.execute(ctx, query="NOTFOUND", file_pattern="*.py")
        assert "No files found" in result.content


# ============================================================
#  Shell tools — pwd
# ============================================================

class TestPwd:
    @pytest.mark.asyncio
    async def test_returns_directory(self):
        env = MockEnvironment(exec_results={"pwd": "/home/user/project\n"})
        ctx = _make_ctx(env=env)
        result = await pwd.execute(ctx)
        assert result.content == "/home/user/project"


# ============================================================
#  Shell tools — git_show
# ============================================================

class TestGitShow:
    @pytest.mark.asyncio
    async def test_show_head(self):
        env = MockEnvironment(exec_results={
            "git show --stat HEAD": "commit abc123\n 3 ++-\n",
        })
        ctx = _make_ctx(env=env)
        result = await git_show.execute(ctx)
        assert "commit" in result.content

    @pytest.mark.asyncio
    async def test_show_specific_ref(self):
        env = MockEnvironment(exec_results={
            "git show --stat v1.0": "tag v1.0\n",
        })
        ctx = _make_ctx(env=env)
        result = await git_show.execute(ctx, ref="v1.0")
        assert "v1.0" in result.content


# ============================================================
#  Shell tools — git_checkout
# ============================================================

class TestGitCheckout:
    @pytest.mark.asyncio
    async def test_checkout_branch(self):
        env = MockEnvironment(exec_results={
            "git checkout feature-x": "Switched to branch 'feature-x'\n",
        })
        ctx = _make_ctx(env=env)
        result = await git_checkout.execute(ctx, branch="feature-x")
        assert "Switched" in result.content


# ============================================================
#  Shell tools — git_create_branch
# ============================================================

class TestGitCreateBranch:
    @pytest.mark.asyncio
    async def test_create_branch(self):
        env = MockEnvironment(exec_results={
            "git checkout -b codeminions/abc123": "Switched to a new branch 'codeminions/abc123'\n",
        })
        ctx = _make_ctx(env=env)
        result = await git_create_branch.execute(ctx, branch="codeminions/abc123")
        assert "new branch" in result.content

    @pytest.mark.asyncio
    async def test_create_branch_from_point(self):
        env = MockEnvironment(exec_results={
            "git checkout -b hotfix v1.0": "Switched to a new branch 'hotfix'\n",
        })
        ctx = _make_ctx(env=env)
        result = await git_create_branch.execute(ctx, branch="hotfix", start_point="v1.0")
        assert "new branch" in result.content


# ============================================================
#  Shell tools — git_push
# ============================================================

class TestGitPush:
    @pytest.mark.asyncio
    async def test_push_with_upstream(self):
        env = MockEnvironment(exec_results={
            "git push -u origin feature-x": "remote: Create PR at https://...",
        })
        ctx = _make_ctx(env=env)
        result = await git_push.execute(ctx, branch="feature-x")
        assert "PR" in result.content or "remote" in result.content

    @pytest.mark.asyncio
    async def test_push_no_upstream(self):
        env = MockEnvironment(exec_results={
            "git push origin main": "Everything up-to-date\n",
        })
        ctx = _make_ctx(env=env)
        result = await git_push.execute(ctx, set_upstream=False, branch="main")
        assert "up-to-date" in result.content


# ============================================================
#  CI tools — summarize_failure_output
# ============================================================

class TestSummarizeFailureOutput:
    @pytest.mark.asyncio
    async def test_empty_input(self):
        ctx = _make_ctx()
        result = await summarize_failure_output.execute(ctx, failure_text="")
        assert "empty" in result.content

    @pytest.mark.asyncio
    async def test_pytest_failure(self):
        ctx = _make_ctx()
        failure = (
            "============================= test session starts ==============================\n"
            "collected 42 items\n\n"
            "tests/test_auth.py F                                                     [ 50%]\n"
            "tests/test_api.py .                                                      [100%]\n"
            "=================================== FAILURES ===================================\n"
            "______________________________ test_login ______________________________\n"
            "tests/test_auth.py:15: in test_login\n"
            "    assert response.status_code == 200\n"
            "E   assert 500 == 200\n"
            "=========================== short test summary info ============================\n"
            "FAILED tests/test_auth.py::test_login - assert 500 == 200\n"
            "========================= 1 failed, 41 passed in 2.3s =========================\n"
        )
        result = await summarize_failure_output.execute(ctx, failure_text=failure)
        assert "Failure summary" in result.content
        assert "test_auth.py" in result.content

    @pytest.mark.asyncio
    async def test_lint_failure(self):
        ctx = _make_ctx()
        failure = (
            "src/app.py:10:5: F841 local variable 'x' is assigned to but never used\n"
            "src/app.py:20:1: E302 expected 2 blank lines\n"
            "Found 2 errors.\n"
        )
        result = await summarize_failure_output.execute(ctx, failure_text=failure, max_items=5)
        assert "Failure summary" in result.content
        assert "F841" in result.content

    @pytest.mark.asyncio
    async def test_limits_output(self):
        ctx = _make_ctx()
        # Generate 100 error lines
        lines = [f"src/file{i}.py:{i}: error F{i}" for i in range(100)]
        failure = "\n".join(lines)
        result = await summarize_failure_output.execute(ctx, failure_text=failure, max_items=5)
        assert "5 items" in result.content
        # Should not include all 100
        assert "file5" not in result.content


# ============================================================
#  Tool subsets — verify new tools are included
# ============================================================

class TestToolSubsets:
    def test_code_tools_has_all_new_tools(self):
        from codeminions.tools import CODE_TOOLS
        names = {t.name for t in CODE_TOOLS}
        for name in [
            "read_file", "write_file", "edit_file", "append_file",
            "insert_before", "insert_after", "replace_regex",
            "file_exists", "grep", "glob", "list_dir",
        ]:
            assert name in names, f"CODE_TOOLS missing {name}"

    def test_shell_tools_has_all_new_tools(self):
        from codeminions.tools import SHELL_TOOLS
        names = {t.name for t in SHELL_TOOLS}
        for name in [
            "run_command", "pwd",
            "git_diff", "git_log", "git_status", "git_show",
            "git_add", "git_commit", "git_create_branch",
            "git_checkout", "git_push", "diff_history",
        ]:
            assert name in names, f"SHELL_TOOLS missing {name}"

    def test_ci_tools_has_summarize_failure(self):
        from codeminions.tools import CI_TOOLS
        names = {t.name for t in CI_TOOLS}
        assert "summarize_failure_output" in names

    def test_search_tools_exists(self):
        from codeminions.tools import SEARCH_TOOLS
        names = {t.name for t in SEARCH_TOOLS}
        assert "find_files" in names
        assert "search_files" in names
        assert len(SEARCH_TOOLS) == 2

    def test_public_api_exports_search_tools(self):
        from codeminions.tools import SEARCH_TOOLS
        assert len(SEARCH_TOOLS) == 2
