"""
Example 03 — Airbnb Migration Pattern
========================================
Large-scale codemod across many files. One agent per file, validated per file.
Inspired by Airbnb: 3,500 React test files migrated in 6 weeks vs 1.5 years manual.

Pattern:
    discover_targets → [per file: migrate → validate]* → summary

Key insights from Airbnb:
- "Selecting correct related files mattered more than prompt engineering"
- Retry logic with dynamic context beats optimised single-shot prompts
- Files move through stages only on passing validation — no bulk failures
- 97% automated success. Some files needed 50-100 retries.
- Each file is independent — process them, track success/failure per file

What this example proves:
- LoopNode iterates a sub-Blueprint over a discovered list
- Per-item state via bind= (current target injected each iteration)
- Failures tracked per item — loop continues on individual failures
- Sub-blueprints are reusable workflow units
"""

from pydantic import BaseModel

from minion import (
    AgentNode,
    Blueprint,
    DeterministicNode,
    LoopNode,
    Minion,
    RunContext,
)
from minion.tools import CODE_TOOLS, SHELL_TOOLS


class MigrationState(BaseModel):
    targets: list[str] = []
    current_target: str = ""
    migrated: list[str] = []
    failed: list[str] = []
    current_error: str = ""


# --- Discover phase ---

async def discover_targets(ctx: RunContext) -> None:
    """Find all files that need migration."""
    result = await ctx.exec("rg -l 'Enzyme\\|shallow\\|mount' tests/")
    ctx.state.targets = [
        line.strip() for line in result.stdout.splitlines() if line.strip()
    ]
    ctx.log(f"Discovered {len(ctx.state.targets)} files to migrate")


# --- Per-file sub-blueprint ---

async def validate_migration(ctx: RunContext) -> None:
    """Validate the current file compiles and tests pass."""
    result = await ctx.exec(f"pytest {ctx.state.current_target} --tb=short -q")
    if result.exit_code == 0:
        ctx.state.migrated.append(ctx.state.current_target)
        ctx.state.current_error = ""
    else:
        ctx.state.failed.append(ctx.state.current_target)
        ctx.state.current_error = result.stdout


per_file_blueprint = Blueprint(
    name="per_file",
    nodes=[
        AgentNode(
            "migrate_file",
            system_prompt=(
                "Migrate the file at ctx.state.current_target from Enzyme to React Testing Library.\n"
                "Rules:\n"
                "- Replace shallow() and mount() with render() from @testing-library/react\n"
                "- Replace enzyme assertions with @testing-library/jest-dom matchers\n"
                "- Keep test intent identical — do not change what is being tested\n"
                "- Do not modify files other than the current target\n"
                "Call done() when the migration is complete."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=40,
            token_budget=20_000,
            max_rounds=3,           # up to 3 attempts per file
            on_max_rounds="continue",  # skip file, mark as failed, keep going
        ),
        DeterministicNode("validate", fn=validate_migration),
    ],
)


# --- Summary ---

async def print_summary(ctx: RunContext) -> None:
    total = len(ctx.state.targets)
    ok = len(ctx.state.migrated)
    failed = len(ctx.state.failed)
    ctx.log(f"Migration complete: {ok}/{total} succeeded, {failed} failed")
    if ctx.state.failed:
        ctx.log(f"Failed files: {ctx.state.failed}")


# --- Main blueprint ---

migration_blueprint = Blueprint(
    name="airbnb_migration",
    state_cls=MigrationState,
    nodes=[
        DeterministicNode("discover", fn=discover_targets),

        LoopNode(
            "migrate_all",
            sub_blueprint=per_file_blueprint,
            iterate_over=lambda ctx: ctx.state.targets,
            bind=lambda ctx, target: setattr(ctx.state, "current_target", target),
            max_iterations=500,
            on_failure="continue",   # one file fails → keep going
        ),

        DeterministicNode("summary", fn=print_summary),
    ],
)


async def main():
    result = await Minion(
        model="claude-sonnet-4-6",
        blueprint=migration_blueprint,
        environment="local",
    ).run(
        "Migrate all Enzyme tests to React Testing Library",
    )

    print(f"outcome  : {result.outcome}")
    print(f"migrated : {len(result.state.migrated)}")
    print(f"failed   : {len(result.state.failed)}")
    print(f"tokens   : {result.tokens}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
