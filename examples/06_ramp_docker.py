"""
Example 06 — Ramp Docker Pattern
===================================
Full-stack isolated environment. Agent runs against real services.
Inspired by Ramp Inspect: Modal sandboxes with Postgres, Redis, full stack local-latency.

Pattern:
    boot_services → gather_context → implement → run_integration_tests → fix? → ship

Key insights from Ramp:
- "No network hop between agent and test suite, no remote filesystem to sync"
- Full stack services (Postgres, Redis) running inside the sandbox
- Pre-built image snapshots for fast startup (30-min cron)
- Agent can take screenshots, navigate real browser (visual verification)
- 80% of Inspect itself was written by Inspect

What this example proves:
- DockerEnv is the production environment (not LocalEnv or GitWorktreeEnv)
- Services start inside the container — real DB, real cache
- Integration tests run against real services (not mocks)
- Environment config is part of the workflow definition
"""

from pydantic import BaseModel

from minion import (
    AgentNode,
    Blueprint,
    DeterministicNode,
    EscalationResult,
    Minion,
    RunContext,
)
from minion.environments import DockerEnv
from minion.tools import CODE_TOOLS, CI_TOOLS, SHELL_TOOLS


class FullStackState(BaseModel):
    branch: str = ""
    services_ready: bool = False
    integration_failed: bool = False
    integration_output: str = ""
    files_changed: list[str] = []


# --- Service lifecycle ---

async def boot_services(ctx: RunContext) -> None:
    """Start required services inside the container."""
    await ctx.exec("pg_ctlcluster 15 main start")
    await ctx.exec("redis-server --daemonize yes")
    await ctx.exec("python manage.py migrate --run-syncdb")

    # Verify services are ready
    pg = await ctx.exec("pg_isready")
    redis = await ctx.exec("redis-cli ping")

    if not (pg.ok and "PONG" in redis.stdout):
        raise RuntimeError("Services failed to start")

    ctx.state.services_ready = True
    ctx.log("Postgres + Redis ready")


async def create_branch(ctx: RunContext) -> None:
    ctx.state.branch = f"minion/{ctx.run_id[:8]}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")


async def run_integration_tests(ctx: RunContext) -> None:
    """Run integration tests against real services — not mocks."""
    result = await ctx.exec(
        "pytest tests/integration/ -x --tb=short -q "
        "--database-url=postgresql://localhost/test_db"
    )
    ctx.state.integration_failed = result.exit_code != 0
    ctx.state.integration_output = result.stdout


async def commit_and_push(ctx: RunContext) -> None:
    await ctx.exec("git add -A")
    await ctx.exec('git commit -m "minion: complete task"')
    await ctx.exec(f"git push -u origin {ctx.state.branch}")
    await ctx.exec(
        f'gh pr create --title "minion: {ctx.task.description[:72]}" '
        f'--body "Tested against real Postgres + Redis in Docker" '
        f'--head {ctx.state.branch}'
    )


ramp_blueprint = Blueprint(
    name="ramp_docker",
    state_cls=FullStackState,
    nodes=[
        DeterministicNode("boot_services",  fn=boot_services),
        DeterministicNode("create_branch",  fn=create_branch),

        AgentNode(
            "implement",
            system_prompt=(
                "You are working in a full-stack Docker environment.\n"
                "Postgres (port 5432) and Redis (port 6379) are running and ready.\n"
                "You can run migrations, seed data, and execute integration tests.\n"
                "Complete the task. Call done() when finished."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS, *CI_TOOLS],
            max_iterations=80,
            token_budget=60_000,
        ),

        DeterministicNode("integration_test", fn=run_integration_tests),

        AgentNode(
            "fix_integration",
            system_prompt=(
                "Integration tests are failing against real services. "
                "Fix the failures shown. You have access to Postgres and Redis. "
                "You may inspect the database state."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: ctx.state.integration_failed,
            max_rounds=2,
            on_max_rounds="escalate",
            token_budget=30_000,
        ),

        DeterministicNode("ship", fn=commit_and_push),
    ],
)


async def main():
    # DockerEnv: each run gets an isolated container with the full stack
    env = DockerEnv(
        image="myapp/dev:latest",        # pre-built image with Postgres, Redis, app deps
        repo_path="./",
        working_dir="/workspace",
        env_file=".env.test",
        network="none",                  # no outbound internet — safe for unattended
        memory_limit="4g",
    )

    result = await Minion(
        model="claude-sonnet-4-6",
        blueprint=ramp_blueprint,
        environment=env,
    ).run("Add Redis-based rate limiting to the payment processing endpoint")

    if isinstance(result, EscalationResult):
        print(f"Escalated: {result.reason}")
        return

    print(f"outcome  : {result.outcome}")
    print(f"branch   : {result.branch}")
    print(f"tokens   : {result.tokens}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
