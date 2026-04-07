"""
Example 04 — LinkedIn Spec-Driven Pattern
==========================================
Structured Task as a contract. Agent operates within explicit boundaries.
Inspired by LinkedIn's agent platform: specification over free-form prompts.

Example type:
- Research example
- Pressure test of `Task` as a specification contract
- Approximation of spec-driven execution inside Minion's unattended runner

Pattern:
    validate_spec → implement → verify_acceptance → judge → ship

What is directly modeled:
- "Specification-as-contract, not free-form prompts"
- Explicit forbidden actions are part of the spec — not guardrails bolted on later
- Acceptance criteria gives the agent a binary signal for done
- Deterministic validation before agent execution

What is approximated:
- organizational authority gates are represented here as a deterministic ship step, not a full deployment/approval system
- institutional memory and execution-tier orchestration are represented through task fields and blueprint structure rather than a separate control plane

What this example proves:
- Task carries structured context: constraints, acceptance, metadata
- ctx.task.constraints used in system prompt (agent is aware of limits)
- ctx.task.acceptance used in verify node (binary done signal)
- DeterministicNode validates spec before agent starts — fail fast
"""

from pydantic import BaseModel

from codeminions import (
    AgentNode,
    Blueprint,
    DeterministicNode,
    EscalationResult,
    JudgeNode,
    Minion,
    RunContext,
    Task,
)
from codeminions.tools import CODE_TOOLS, SHELL_TOOLS


class SpecState(BaseModel):
    branch: str = ""
    spec_valid: bool = False
    acceptance_passed: bool = False
    files_changed: list[str] = []


# --- Spec validation ---

async def validate_spec(ctx: RunContext) -> None:
    """Reject the run immediately if the spec is incomplete."""
    if not ctx.task.acceptance:
        raise ValueError(
            f"Task '{ctx.task.description}' has no acceptance criteria. "
            f"Add Task(acceptance='...') before running."
        )
    ctx.state.branch = f"codeminions/{ctx.run_id[:8]}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")
    ctx.state.spec_valid = True


# --- Acceptance verification ---

async def verify_acceptance(ctx: RunContext) -> None:
    """Run the acceptance command from the task spec."""
    result = await ctx.exec(ctx.task.acceptance)
    ctx.state.acceptance_passed = result.exit_code == 0
    if not ctx.state.acceptance_passed:
        ctx.log(f"Acceptance check failed: {result.stdout}")


async def ship(ctx: RunContext) -> None:
    await ctx.exec("git add -A")
    await ctx.exec('git commit -m "minion: complete task"')
    await ctx.exec(f"git push -u origin {ctx.state.branch}")
    await ctx.exec(
        f'gh pr create --title "minion: {ctx.task.description[:72]}" '
        f'--body "**Acceptance:** `{ctx.task.acceptance}`\n\nAutomated by CodeMinions" '
        f'--head {ctx.state.branch}'
    )


spec_blueprint = Blueprint(
    name="linkedin_spec",
    state_cls=SpecState,
    nodes=[
        # Fail fast if spec is incomplete — before any tokens spent
        DeterministicNode("validate_spec", fn=validate_spec),

        AgentNode(
            "implement",
            # Constraints from the Task spec are injected into the system prompt
            system_prompt=(
                "You are implementing a task according to a strict specification.\n\n"
                "TASK: {task.description}\n\n"
                "ACCEPTANCE CRITERIA: {task.acceptance}\n\n"
                "CONSTRAINTS (you must not violate these):\n{task.constraints_list}\n\n"
                "CONTEXT FILES: {task.context_list}\n\n"
                "Call done() only when the acceptance criteria passes."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=80,
            token_budget=60_000,
            max_rounds=2,
        ),

        # Binary acceptance check — the spec says how to verify
        DeterministicNode("verify", fn=verify_acceptance),

        AgentNode(
            "fix_acceptance",
            system_prompt=(
                "The acceptance check failed. Fix the implementation until "
                "`{task.acceptance}` passes. Do not change unrelated code."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: not ctx.state.acceptance_passed,
            max_rounds=2,
            on_max_rounds="escalate",
            token_budget=30_000,
        ),

        JudgeNode(
            name="spec_judge",
            evaluates="implement",
            criteria=(
                "The implementation satisfies the task description. "
                "No forbidden actions from the constraints were taken. "
                "Only files in the context list or directly required by the task were modified."
            ),
            on_veto="retry",
            max_vetoes=1,
        ),

        DeterministicNode("ship", fn=ship),
    ],
)


async def main():
    # Structured task — this is the LinkedIn pattern
    task = Task(
        description="Add JWT refresh token rotation to the auth service",
        context=[
            "src/auth/tokens.py",
            "src/auth/middleware.py",
            "tests/test_auth.py",
        ],
        acceptance="pytest tests/test_auth.py -k 'refresh' -v",
        constraints=[
            "Do not modify the database schema",
            "Do not change the public Token API interface",
            "Do not modify any files outside src/auth/ and tests/",
        ],
    )

    result = await Minion(
        model="claude-sonnet-4-6",
        blueprint=spec_blueprint,
        environment="local",
    ).run(task)

    if isinstance(result, EscalationResult):
        print(f"Escalated: {result.reason}")
        return

    print(f"outcome    : {result.outcome}")
    print(f"branch     : {result.branch}")
    print(f"acceptance : {result.state.acceptance_passed}")
    print(f"tokens     : {result.tokens}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
