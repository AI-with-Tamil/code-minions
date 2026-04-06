"""
Example 08 — Real LLM End-to-End Smoke Run
==========================================
Runs Minion against a temporary git repo with a real model.

Why this exists:
- exercises the actual model adapter, tool loop, environment, and blueprint
- avoids mutating the current repo
- avoids `git push` / `gh pr create` side effects
- gives a repeatable end-to-end sanity check before larger real runs

Usage:
    ANTHROPIC_API_KEY=... uv run python examples/08_real_llm_smoke.py
    OPENAI_API_KEY=... uv run python examples/08_real_llm_smoke.py --model gpt-4o
"""

from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import tempfile
from pathlib import Path

from pydantic import BaseModel

from minion import AgentNode, Blueprint, DeterministicNode, Minion, RunContext, Task
from minion.environments import LocalEnv
from minion.tools import CODE_TOOLS, SHELL_TOOLS


class SmokeState(BaseModel):
    branch: str = ""
    tests_passed: bool = False
    test_output: str = ""


def _choose_model(explicit: str | None) -> str:
    if explicit:
        return explicit
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "claude-sonnet-4-6"
    if os.environ.get("OPENAI_API_KEY"):
        return "gpt-4o"
    raise RuntimeError(
        "No real model configured. Set ANTHROPIC_API_KEY or OPENAI_API_KEY, "
        "or pass --model explicitly."
    )


def _run(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
    if proc.stdout.strip():
        print(proc.stdout.strip())


def _write_repo(root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)

    (root / "src" / "app.py").write_text(
        "def sanitize_username(value: str) -> str:\n"
        "    return value.strip().lower()\n",
        encoding="utf-8",
    )

    (root / "tests" / "test_app.py").write_text(
        "from src.app import normalize_email, sanitize_username\n\n"
        "def test_sanitize_username():\n"
        "    assert sanitize_username('  Alice  ') == 'alice'\n\n"
        "def test_normalize_email_lowercases_and_trims():\n"
        "    assert normalize_email('  ALICE@example.COM  ') == 'alice@example.com'\n\n"
        "def test_normalize_email_returns_empty_for_blank():\n"
        "    assert normalize_email('   ') == ''\n",
        encoding="utf-8",
    )


def _init_git_repo(root: Path) -> None:
    _run(["git", "init", "-b", "main"], cwd=root)
    _run(["git", "config", "user.name", "Minion Smoke"], cwd=root)
    _run(["git", "config", "user.email", "minion-smoke@example.com"], cwd=root)
    _run(["git", "add", "."], cwd=root)
    _run(["git", "commit", "-m", "chore: seed smoke repo"], cwd=root)


async def create_branch(ctx: RunContext) -> None:
    ctx.state.branch = f"minion/{ctx.run_id[:8]}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")


async def run_tests(ctx: RunContext) -> None:
    result = await ctx.exec("pytest -q")
    ctx.state.tests_passed = result.exit_code == 0
    ctx.state.test_output = result.stdout + result.stderr
    if not ctx.state.tests_passed:
        ctx.log(ctx.state.test_output)


smoke_blueprint = Blueprint(
    name="real_llm_smoke",
    state_cls=SmokeState,
    nodes=[
        DeterministicNode("create_branch", fn=create_branch),
        AgentNode(
            "implement",
            system_prompt=(
                "You are working in a small Python repo.\n"
                "Implement only what the task requires.\n"
                "Keep changes minimal and production-quality.\n"
                "Call done() when finished."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=40,
            token_budget=25_000,
        ),
        DeterministicNode("test", fn=run_tests),
    ],
)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=None, help="Model string, e.g. claude-sonnet-4-6 or gpt-4o")
    args = parser.parse_args()

    model = _choose_model(args.model)

    with tempfile.TemporaryDirectory(prefix="minion-smoke-") as tmp:
        repo = Path(tmp)
        _write_repo(repo)
        _init_git_repo(repo)

        task = Task(
            description="Add normalize_email(value: str) to src/app.py so the tests pass.",
            context=["src/app.py", "tests/test_app.py"],
            acceptance="pytest -q",
            constraints=[
                "Only modify src/app.py unless absolutely necessary",
                "Do not change the tests",
            ],
        )

        print(f"temp repo : {repo}")
        print(f"model     : {model}")

        result = await Minion(
            model=model,
            blueprint=smoke_blueprint,
            environment=LocalEnv(str(repo)),
        ).run(task)

        print(f"outcome   : {result.outcome}")
        print(f"branch    : {result.branch}")
        print(f"tokens    : {result.tokens}")
        print(f"duration  : {result.duration_ms}ms")
        print(f"summary   : {result.summary}")
        print(f"tests_ok  : {result.state.tests_passed}")
        print("\n--- diff ---")
        print(result.diff.strip() or "<no diff>")

        if not result.state.tests_passed:
            print("\n--- test output ---")
            print(result.state.test_output.strip())


if __name__ == "__main__":
    asyncio.run(main())
