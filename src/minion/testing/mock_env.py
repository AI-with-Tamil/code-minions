"""MockEnvironment — in-memory filesystem and command execution."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field

from minion.core.context import ExecResult


class MockCommandNotFoundError(Exception):
    """Raised when exec() receives a command not in exec_results."""


@dataclass
class EnvCall:
    """Record of an environment operation."""
    method: str
    args: tuple
    kwargs: dict = field(default_factory=dict)


class MockEnvironment:
    """In-memory filesystem and command execution. No real files or processes.

    - read() returns from files dict; raises FileNotFoundError if missing
    - write() updates files dict in memory
    - edit() applies old→new replacement in files dict
    - exec() matches cmd against exec_results keys (exact match, then glob match)
    - All operations recorded in self.calls
    """

    def __init__(
        self,
        files: dict[str, str] | None = None,
        exec_results: dict[str, int | str] | None = None,
    ) -> None:
        self.files = dict(files) if files else {}
        self.exec_results = dict(exec_results) if exec_results else {}
        self.calls: list[EnvCall] = []
        self.path = "/mock"

    async def read(self, path: str) -> str:
        self.calls.append(EnvCall("read", (path,)))
        if path not in self.files:
            raise FileNotFoundError(f"MockEnvironment: file not found: {path}")
        return self.files[path]

    async def write(self, path: str, content: str) -> None:
        self.calls.append(EnvCall("write", (path, content)))
        self.files[path] = content

    async def edit(self, path: str, old: str, new: str) -> None:
        self.calls.append(EnvCall("edit", (path, old, new)))
        if path not in self.files:
            raise FileNotFoundError(f"MockEnvironment: file not found: {path}")
        content = self.files[path]
        if old not in content:
            raise ValueError(f"MockEnvironment: old_string not found in {path}")
        self.files[path] = content.replace(old, new, 1)

    async def exec(self, cmd: str, cwd: str | None = None) -> ExecResult:
        self.calls.append(EnvCall("exec", (cmd,), {"cwd": cwd}))

        # Exact match first
        if cmd in self.exec_results:
            return self._make_result(cmd, self.exec_results[cmd])

        # Glob match
        for pattern, result_val in self.exec_results.items():
            if fnmatch.fnmatch(cmd, pattern):
                return self._make_result(cmd, result_val)

        # Default: return success for common git commands to reduce test verbosity
        if cmd.startswith("git "):
            return ExecResult(stdout="", stderr="", exit_code=0)

        raise MockCommandNotFoundError(
            f"MockEnvironment: command not found in exec_results: {cmd!r}\n"
            f"Available patterns: {list(self.exec_results.keys())}"
        )

    async def glob(self, pattern: str) -> list[str]:
        self.calls.append(EnvCall("glob", (pattern,)))
        return [p for p in sorted(self.files.keys()) if fnmatch.fnmatch(p, pattern)]

    async def exists(self, path: str) -> bool:
        self.calls.append(EnvCall("exists", (path,)))
        return path in self.files

    async def cleanup(self) -> None:
        self.calls.append(EnvCall("cleanup", ()))

    def _make_result(self, cmd: str, val: int | str) -> ExecResult:
        if isinstance(val, int):
            return ExecResult(stdout="", stderr="", exit_code=val)
        # String value = stdout with exit code 0
        return ExecResult(stdout=val, stderr="", exit_code=0)
