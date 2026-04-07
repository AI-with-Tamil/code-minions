"""DockerEnv lifecycle unit tests — no real Docker daemon required."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from codeminions.environments.docker import DockerEnv, _find_free_port, _load_env_file


# ---------------------------------------------------------------------------
# _load_env_file
# ---------------------------------------------------------------------------

def test_load_env_file_parses_simple_pairs(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("KEY=value\nFOO=bar\n", encoding="utf-8")
    result = _load_env_file(str(tmp_path / ".env"))
    assert result == {"KEY": "value", "FOO": "bar"}


def test_load_env_file_skips_comments_and_blanks(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "# comment\n\nKEY=value\n  # indented comment\n",
        encoding="utf-8",
    )
    result = _load_env_file(str(tmp_path / ".env"))
    assert result == {"KEY": "value"}


def test_load_env_file_strips_quotes(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        'DOUBLE="hello world"\nSINGLE=\'bye world\'\n',
        encoding="utf-8",
    )
    result = _load_env_file(str(tmp_path / ".env"))
    assert result == {"DOUBLE": "hello world", "SINGLE": "bye world"}


def test_load_env_file_handles_empty_value(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("EMPTY=\n", encoding="utf-8")
    result = _load_env_file(str(tmp_path / ".env"))
    assert result == {"EMPTY": ""}


def test_load_env_file_missing_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="env_file not found"):
        _load_env_file(str(tmp_path / "nonexistent.env"))


def test_load_env_file_value_with_equals(tmp_path: Path) -> None:
    # Value itself contains '=' — only first '=' is the separator
    (tmp_path / ".env").write_text("URL=https://example.com/path?a=1&b=2\n", encoding="utf-8")
    result = _load_env_file(str(tmp_path / ".env"))
    assert result == {"URL": "https://example.com/path?a=1&b=2"}


# ---------------------------------------------------------------------------
# _find_free_port
# ---------------------------------------------------------------------------

def test_find_free_port_returns_port_in_range() -> None:
    port = _find_free_port((40000, 50000))
    assert 40000 <= port < 50000


def test_find_free_port_port_is_actually_free() -> None:
    port = _find_free_port((40000, 50000))
    # Verify we can bind it ourselves
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", port))  # should not raise


def test_find_free_port_raises_on_empty_range() -> None:
    with pytest.raises(RuntimeError, match="No free port"):
        _find_free_port((9999, 9999))  # start == end → zero iterations


# ---------------------------------------------------------------------------
# DockerEnv dataclass defaults
# ---------------------------------------------------------------------------

def test_dockerenv_defaults() -> None:
    env = DockerEnv(image="python:3.12", repo_path="/tmp/repo")
    assert env.working_dir == "/workspace"
    assert env.env_file is None
    assert env.network == "none"
    assert env.port_range == (40000, 50000)
    assert env.memory_limit == "4g"
    assert env.cpu_limit == 2.0
    assert env.startup_commands == []
    assert env._container_id is None
    assert env._reserved_port is None


def test_dockerenv_startup_commands_stored() -> None:
    cmds = ["pip install -e .", "python -c 'import app'"]
    env = DockerEnv(image="python:3.12", repo_path="/tmp/repo", startup_commands=cmds)
    assert env.startup_commands == cmds


def test_dockerenv_exec_raises_without_setup() -> None:
    env = DockerEnv(image="python:3.12", repo_path="/tmp/repo")

    import asyncio

    with pytest.raises(RuntimeError, match="not set up"):
        asyncio.run(env.exec("echo hi"))


def test_dockerenv_write_raises_without_setup() -> None:
    env = DockerEnv(image="python:3.12", repo_path="/tmp/repo")

    import asyncio

    with pytest.raises(RuntimeError, match="not set up"):
        asyncio.run(env.write("file.txt", "content"))


# ---------------------------------------------------------------------------
# WorktreePool unit tests (no real git repo needed)
# ---------------------------------------------------------------------------

import asyncio
from unittest.mock import AsyncMock, patch

from codeminions.environments.worktree import GitWorktreeEnv, WorktreePool


def test_gitworktreeenv_pool_none_when_pool_size_1() -> None:
    env = GitWorktreeEnv(repo_path="/tmp/repo", pool_size=1)
    assert env._pool is None


def test_gitworktreeenv_pool_created_when_pool_size_gt_1() -> None:
    env = GitWorktreeEnv(repo_path="/tmp/repo", pool_size=3)
    assert env._pool is not None
    assert isinstance(env._pool, WorktreePool)


def test_gitworktreeenv_pool_property_raises_when_size_1() -> None:
    env = GitWorktreeEnv(repo_path="/tmp/repo", pool_size=1)
    with pytest.raises(RuntimeError, match="pool_size > 1"):
        _ = env.pool


def test_gitworktreeenv_pool_property_accessible_when_size_gt_1() -> None:
    env = GitWorktreeEnv(repo_path="/tmp/repo", pool_size=2)
    assert env.pool is env._pool


@pytest.mark.asyncio
async def test_worktreepool_warm_populates_queue() -> None:
    pool = WorktreePool(
        repo_path="/tmp/repo",
        base_branch="main",
        prefix="test",
        size=3,
    )
    with patch(
        "codeminions.environments.worktree._create_worktree",
        new=AsyncMock(side_effect=[
            ("/tmp/wt1", "test/aa"),
            ("/tmp/wt2", "test/bb"),
            ("/tmp/wt3", "test/cc"),
        ]),
    ):
        await pool.warm()

    assert pool._queue.qsize() == 3


@pytest.mark.asyncio
async def test_worktreepool_acquire_uses_queue_first() -> None:
    pool = WorktreePool(repo_path="/tmp/repo", base_branch="main", prefix="t", size=2)
    pool._queue.put_nowait(("/tmp/wt1", "t/x"))

    with patch(
        "codeminions.environments.worktree._create_worktree",
        new=AsyncMock(return_value=("/tmp/new", "t/new")),
    ) as mock_create:
        path, branch = await pool.acquire()

    assert path == "/tmp/wt1"
    assert branch == "t/x"
    mock_create.assert_not_called()  # queue had items, no creation needed


@pytest.mark.asyncio
async def test_worktreepool_acquire_creates_on_empty_queue() -> None:
    pool = WorktreePool(repo_path="/tmp/repo", base_branch="main", prefix="t", size=2)
    # queue is empty

    with patch(
        "codeminions.environments.worktree._create_worktree",
        new=AsyncMock(return_value=("/tmp/new", "t/new")),
    ) as mock_create:
        path, branch = await pool.acquire()

    assert path == "/tmp/new"
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_worktreepool_release_returns_to_queue_when_under_capacity() -> None:
    pool = WorktreePool(repo_path="/tmp/repo", base_branch="main", prefix="t", size=2)

    with patch("codeminions.environments.worktree._reset_worktree", new=AsyncMock()) as mock_reset:
        await pool.release("/tmp/wt1", "t/x")

    mock_reset.assert_called_once_with("/tmp/repo", "/tmp/wt1", "main")
    assert pool._queue.qsize() == 1


@pytest.mark.asyncio
async def test_worktreepool_release_removes_when_at_capacity() -> None:
    pool = WorktreePool(repo_path="/tmp/repo", base_branch="main", prefix="t", size=1)
    pool._queue.put_nowait(("/tmp/existing", "t/y"))  # queue already full

    with patch("codeminions.environments.worktree._remove_worktree", new=AsyncMock()) as mock_rm:
        with patch("codeminions.environments.worktree._reset_worktree", new=AsyncMock()) as mock_reset:
            await pool.release("/tmp/wt1", "t/x")

    mock_rm.assert_called_once_with("/tmp/repo", "/tmp/wt1")
    mock_reset.assert_not_called()
    assert pool._queue.qsize() == 1  # original item unchanged


@pytest.mark.asyncio
async def test_worktreepool_close_drains_queue() -> None:
    pool = WorktreePool(repo_path="/tmp/repo", base_branch="main", prefix="t", size=3)
    pool._queue.put_nowait(("/tmp/wt1", "t/a"))
    pool._queue.put_nowait(("/tmp/wt2", "t/b"))

    with patch("codeminions.environments.worktree._remove_worktree", new=AsyncMock()) as mock_rm:
        await pool.close()

    assert mock_rm.call_count == 2
    assert pool._queue.empty()
