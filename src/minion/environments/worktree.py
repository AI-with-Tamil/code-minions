"""GitWorktreeEnv — code isolation via git worktrees. Local dev only."""

from __future__ import annotations

import asyncio
import glob as globmod
import os
import uuid
from pathlib import Path

from minion.core.context import ExecResult


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

    @property
    def path(self) -> str:
        return self._worktree_path or self._repo_path

    async def setup(self) -> None:
        """Create a worktree for this run."""
        suffix = uuid.uuid4().hex[:8]
        self._branch_name = f"{self._branch_prefix}/{suffix}"
        self._worktree_path = os.path.join(
            self._repo_path, ".worktrees", self._branch_name.replace("/", "-")
        )
        os.makedirs(os.path.dirname(self._worktree_path), exist_ok=True)
        proc = await asyncio.create_subprocess_shell(
            f"git worktree add -b {self._branch_name} {self._worktree_path} {self._base_branch}",
            cwd=self._repo_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()

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
        if self._cleanup_on_complete and self._worktree_path:
            proc = await asyncio.create_subprocess_shell(
                f"git worktree remove --force {self._worktree_path}",
                cwd=self._repo_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

    def _resolve(self, path: str) -> str:
        if os.path.isabs(path):
            return path
        return os.path.join(self.path, path)
