"""
Example 07 — Coinbase Council Pattern
========================================
Multiple specialized agents validate each other before work proceeds.
Inspired by Coinbase Cloudbot: agent councils and typed interfaces between specialized checks.

Pattern:
    implement → security_review → correctness_review → (fix if vetoed)? → test → ship

Key insights from Coinbase:
- Code-first workflows with typed interfaces between agents
- Agent councils: multiple specialized agents validate each other's output
- Each council member has a specific domain: security, correctness, performance
- "Design the handoff and feedback loop into the UX"
- First-class observability attached to every node

Difference from Spotify JudgeNode (Example 02):
- JudgeNode: single general-purpose LLM evaluates the diff holistically
- Council: multiple SPECIALIZED agents each own a domain
  - SecurityAgent: looks only for security vulnerabilities
  - CorrectnessAgent: looks only for logic correctness
  Both can veto independently. Fix agent sees both verdicts.

What this example proves:
- Multiple JudgeNodes with domain-specific criteria
- Structured council feedback via state (each judge writes to its own field)
- Council rejection triggers a targeted fix (agent sees which council member vetoed)
- ParallelNode for running multiple reviewers concurrently (faster)
"""

from pydantic import BaseModel

from minion import (
    AgentNode,
    Blueprint,
    DeterministicNode,
    EscalationResult,
    JudgeNode,
    Minion,
    ParallelNode,
    RunContext,
)
from minion.tools import CODE_TOOLS, SHELL_TOOLS


class CouncilState(BaseModel):
    branch: str = ""
    security_verdict: str = ""         # "approved" | "vetoed: <reason>"
    correctness_verdict: str = ""
    council_passed: bool = False
    tests_failed: bool = False
    test_output: str = ""
    files_changed: list[str] = []


async def create_branch(ctx: RunContext) -> None:
    ctx.state.branch = f"minion/{ctx.run_id[:8]}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")


async def evaluate_council(ctx: RunContext) -> None:
    """Aggregate council verdicts into a single pass/fail."""
    security_ok = ctx.state.security_verdict == "approved"
    correctness_ok = ctx.state.correctness_verdict == "approved"
    ctx.state.council_passed = security_ok and correctness_ok

    if not ctx.state.council_passed:
        reasons = []
        if not security_ok:
            reasons.append(f"Security: {ctx.state.security_verdict}")
        if not correctness_ok:
            reasons.append(f"Correctness: {ctx.state.correctness_verdict}")
        ctx.log(f"Council rejected: {'; '.join(reasons)}")


async def run_tests(ctx: RunContext) -> None:
    result = await ctx.exec("pytest tests/ -x --tb=short")
    ctx.state.tests_failed = result.exit_code != 0
    ctx.state.test_output = result.stdout


async def ship(ctx: RunContext) -> None:
    await ctx.exec("git add -A")
    await ctx.exec('git commit -m "minion: complete task"')
    await ctx.exec(f"git push -u origin {ctx.state.branch}")
    await ctx.exec(
        f'gh pr create --title "minion: {ctx.task.description[:72]}" '
        f'--body "Council reviewed: security ✓ correctness ✓" '
        f'--head {ctx.state.branch}'
    )


council_blueprint = Blueprint(
    name="coinbase_council",
    state_cls=CouncilState,
    nodes=[
        DeterministicNode("create_branch", fn=create_branch),

        AgentNode(
            "implement",
            system_prompt=(
                "You are implementing a task in a financial services codebase.\n"
                "This code handles real money. Be precise. Be correct.\n"
                "Call done() when finished."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=80,
            token_budget=60_000,
        ),

        # Both council members review the diff in parallel — faster
        ParallelNode(
            "council_review",
            nodes=[
                JudgeNode(
                    name="security_council",
                    evaluates="implement",
                    criteria=(
                        "Review for security vulnerabilities only:\n"
                        "- No SQL injection, XSS, or injection vulnerabilities\n"
                        "- No credentials, secrets, or API keys in code\n"
                        "- No unsafe deserialization\n"
                        "- No missing authorization checks on financial operations\n"
                        "- Input validation present on all external data\n"
                        "Approve if no security issues found. Veto with specific finding."
                    ),
                    on_veto="retry",
                    max_vetoes=2,
                ),
                JudgeNode(
                    name="correctness_council",
                    evaluates="implement",
                    criteria=(
                        "Review for correctness only:\n"
                        "- Business logic matches the task description exactly\n"
                        "- Edge cases handled (null, empty, overflow)\n"
                        "- No off-by-one errors in financial calculations\n"
                        "- Decimal precision preserved in all monetary values\n"
                        "- Error handling present and correct\n"
                        "Approve if implementation is correct. Veto with specific finding."
                    ),
                    on_veto="retry",
                    max_vetoes=2,
                ),
            ],
        ),

        DeterministicNode("aggregate_verdict", fn=evaluate_council),

        # If council rejected, agent sees both verdicts and fixes specifically
        AgentNode(
            "fix_council_feedback",
            system_prompt=(
                "The council reviewed your implementation and found issues.\n\n"
                "Security verdict: {state.security_verdict}\n"
                "Correctness verdict: {state.correctness_verdict}\n\n"
                "Fix the specific issues raised. Do not change unrelated code."
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: not ctx.state.council_passed,
            max_rounds=2,
            on_max_rounds="escalate",
            token_budget=30_000,
        ),

        DeterministicNode("test", fn=run_tests),

        AgentNode(
            "fix_tests",
            system_prompt="Fix failing tests only.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: ctx.state.tests_failed,
            max_rounds=1,
            on_max_rounds="escalate",
            token_budget=20_000,
        ),

        DeterministicNode("ship", fn=ship),
    ],
)


async def main():
    result = await Minion(
        model="claude-opus-4-6",        # council pattern warrants stronger model
        blueprint=council_blueprint,
        environment="local",
    ).run(
        "Add transaction fee calculation with support for tiered pricing "
        "based on monthly volume"
    )

    if isinstance(result, EscalationResult):
        print(f"Escalated at '{result.node}': {result.reason}")
        return

    print(f"outcome     : {result.outcome}")
    print(f"branch      : {result.branch}")
    print(f"security    : {result.state.security_verdict}")
    print(f"correctness : {result.state.correctness_verdict}")
    print(f"tokens      : {result.tokens}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
