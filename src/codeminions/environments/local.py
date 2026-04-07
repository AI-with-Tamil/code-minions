"""LocalEnv — no isolation, runs directly in the specified directory."""

from __future__ import annotations

import asyncio
import glob as globmod
import os
from pathlib import Path

from codeminions.core.context import ExecResult


class LocalEnv:
    """No isolation. Runs directly in the specified directory.

    Use for local development, example workflows, and blueprint testing.
    Do not treat it as a production unattended environment.
    """

    def __init__(self, path: str = ".") -> None:
        self.path = str(Path(path).resolve())

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
        # Return relative to self.path
        return [os.path.relpath(m, self.path) for m in sorted(matches)]

    async def exists(self, path: str) -> bool:
        full = self._resolve(path)
        return await asyncio.to_thread(os.path.exists, full)

    async def cleanup(self) -> None:
        pass  # LocalEnv has nothing to clean up

    def _resolve(self, path: str) -> str:
        """Resolve path and ensure it stays within self.path (prevent traversal)."""
        # Always join relative to self.path, even for absolute paths
        # This prevents agents from escaping the sandbox via absolute paths
        if os.path.isabs(path):
            # Strip leading slash and treat as relative to self.path
            path = path.lstrip("/")
        full = os.path.normpath(os.path.join(self.path, path))
        # Verify the resolved path is within self.path
        real_base = os.path.realpath(self.path)
        if not full.startswith(real_base + os.sep) and full != real_base:
            raise ValueError(
                f"Path traversal blocked: {path!r} resolves outside sandbox ({self.path})"
            )
        return full
