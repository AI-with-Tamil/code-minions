"""GitWorktreeEnv — code isolation via git worktrees. Local dev only."""

from __future__ import annotations

import asyncio
import glob as globmod
import os
import uuid
from pathlib import Path

from codeminions.core.context import ExecResult


async def _run_git(cmd: str, cwd: str) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_shell(
        cmd,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return proc.returncode or 0, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")


async def _create_worktree(
    repo_path: str,
    base_branch: str,
    prefix: str,
) -> tuple[str, str]:
    """Create a new git worktree. Returns (worktree_path, branch_name)."""
    suffix = uuid.uuid4().hex[:8]
    branch = f"{prefix}/{suffix}"
    path = os.path.join(repo_path, ".worktrees", branch.replace("/", "-"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rc, _, err = await _run_git(
        f"git worktree add -b {branch} {path} {base_branch}",
        repo_path,
    )
    if rc != 0:
        raise RuntimeError(
            f"Failed to create worktree: branch={branch} path={path}\n{err}"
        )
    return path, branch


async def _remove_worktree(repo_path: str, path: str) -> None:
    await _run_git(f"git worktree remove --force {path}", repo_path)


async def _reset_worktree(repo_path: str, path: str, base_branch: str) -> None:
    """Reset worktree to base_branch HEAD so it can be reused."""
    await _run_git(f"git -C {path} reset --hard {base_branch}", repo_path)
    await _run_git(f"git -C {path} clean -fd", repo_path)


class WorktreePool:
    """Manages pre-warmed worktrees for parallel GitWorktreeEnv runs.

    Usage::

        env = GitWorktreeEnv(repo_path="./repo", pool_size=4)
        await env.pool.warm()          # pre-create 4 worktrees

        # run_batch draws from the pool; each run checks out in < 100ms
        results = await Minion(environment=env).run_batch(tasks)

        await env.pool.close()         # remove remaining pooled worktrees
    """

    def __init__(
        self,
        repo_path: str,
        base_branch: str,
        prefix: str,
        size: int,
    ) -> None:
        self._repo_path = repo_path
        self._base_branch = base_branch
        self._prefix = prefix
        self._size = size
        self._queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

    async def warm(self) -> None:
        """Pre-create *size* worktrees so they are ready for immediate checkout."""
        for _ in range(self._size):
            path, branch = await _create_worktree(
                self._repo_path, self._base_branch, self._prefix
            )
            self._queue.put_nowait((path, branch))

    async def acquire(self) -> tuple[str, str]:
        """Return (path, branch) for an available worktree.

        Pulls from the pre-warmed queue if possible; creates a fresh one on demand
        if the queue is empty (e.g. warm() was not called or concurrency exceeded
        pool_size).
        """
        try:
            return self._queue.get_nowait()
        except asyncio.QueueEmpty:
            return await _create_worktree(
                self._repo_path, self._base_branch, self._prefix
            )

    async def release(self, path: str, branch: str) -> None:
        """Return a used worktree to the pool (reset to base branch), or remove it
        if the pool is already at capacity.
        """
        if self._queue.qsize() < self._size:
            await _reset_worktree(self._repo_path, path, self._base_branch)
            self._queue.put_nowait((path, branch))
        else:
            await _remove_worktree(self._repo_path, path)

    async def close(self) -> None:
        """Remove all pooled worktrees. Call when the pool is no longer needed."""
        while not self._queue.empty():
            path, _ = self._queue.get_nowait()
            try:
                await _remove_worktree(self._repo_path, path)
            except Exception:
                pass  # best-effort


class GitWorktreeEnv:
    """Code isolation via git worktrees. Separate branch checkout per run.

    Does NOT isolate ports, databases, or environment variables.
    Use only for local development and testing blueprints.
    """

    def __init__(
        self,
        repo_path: str,
        base_branch: str = "main",
        branch_prefix: str = "minion",
        pool_size: int = 1,
        cleanup_on_complete: bool = True,
    ) -> None:
        self._repo_path = str(Path(repo_path).resolve())
        self._base_branch = base_branch
        self._branch_prefix = branch_prefix
        self._pool_size = pool_size
        self._cleanup_on_complete = cleanup_on_complete
        self._worktree_path: str | None = None
        self._branch_name: str | None = None
        self._pool: WorktreePool | None = (
            WorktreePool(
                repo_path=self._repo_path,
                base_branch=base_branch,
                prefix=branch_prefix,
                size=pool_size,
            )
            if pool_size > 1
            else None
        )

    @property
    def path(self) -> str:
        return self._worktree_path or self._repo_path

    @property
    def pool(self) -> WorktreePool:
        """Access the WorktreePool. Only available when pool_size > 1."""
        if self._pool is None:
            raise RuntimeError(
                "WorktreePool requires pool_size > 1. "
                "Set pool_size=N when constructing GitWorktreeEnv."
            )
        return self._pool

    async def setup(self) -> None:
        """Check out a worktree for this run (from pool if available)."""
        if self._pool is not None:
            self._worktree_path, self._branch_name = await self._pool.acquire()
        else:
            self._worktree_path, self._branch_name = await _create_worktree(
                self._repo_path, self._base_branch, self._branch_prefix
            )

    async def read(self, path: str) -> str:
        full = self._resolve(path)
        if not os.path.exists(full):
            raise FileNotFoundError(f"File not found: {full}")
        return await asyncio.to_thread(Path(full).read_text, encoding="utf-8")

    async def write(self, path: str, content: str) -> None:
        full = self._resolve(path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        await asyncio.to_thread(Path(full).write_text, content, encoding="utf-8")

    async def edit(self, path: str, old: str, new: str) -> None:
        content = await self.read(path)
        if old not in content:
            raise ValueError(f"old_string not found in {path}")
        content = content.replace(old, new, 1)
        await self.write(path, content)

    async def exec(self, cmd: str, cwd: str | None = None) -> ExecResult:
        work_dir = cwd or self.path
        proc = await asyncio.create_subprocess_shell(
            cmd,
            cwd=work_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await proc.communicate()
        return ExecResult(
            stdout=stdout_bytes.decode("utf-8", errors="replace"),
            stderr=stderr_bytes.decode("utf-8", errors="replace"),
            exit_code=proc.returncode or 0,
        )

    async def glob(self, pattern: str) -> list[str]:
        full_pattern = os.path.join(self.path, pattern)
        matches = await asyncio.to_thread(globmod.glob, full_pattern, recursive=True)
        return [os.path.relpath(m, self.path) for m in sorted(matches)]

    async def exists(self, path: str) -> bool:
        full = self._resolve(path)
        return await asyncio.to_thread(os.path.exists, full)

    async def cleanup(self) -> None:
        if self._pool is not None and self._worktree_path and self._branch_name:
            if self._cleanup_on_complete:
                await self._pool.release(self._worktree_path, self._branch_name)
            # if cleanup_on_complete=False: keep the worktree for inspection
        elif self._cleanup_on_complete and self._worktree_path:
            proc = await asyncio.create_subprocess_shell(
                f"git worktree remove --force {self._worktree_path}",
                cwd=self._repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            # cleanup is best-effort — orphan worktrees can be cleaned up manually

    def _resolve(self, path: str) -> str:
        """Resolve path and ensure it stays within self.path (prevent traversal)."""
        if os.path.isabs(path):
            path = path.lstrip("/")
        full = os.path.normpath(os.path.join(self.path, path))
        real_base = os.path.realpath(self.path)
        if not full.startswith(real_base + os.sep) and full != real_base:
            raise ValueError(
                f"Path traversal blocked: {path!r} resolves outside sandbox ({self.path})"
            )
        return full
