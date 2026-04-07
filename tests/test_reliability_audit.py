"""Reliability audit: scenario-parametrized runs of the example 09 blueprint.

Verifies that outcomes, token budgets, and tool call patterns hold across
representative execution paths — without calling real LLMs. Each scenario
records a metrics snapshot; budget assertions catch regressions.

Run with:
    uv run pytest -q tests/test_reliability_audit.py -v
"""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest
from pydantic import BaseModel

from codeminions import EscalationResult, RunResult, Task
from codeminions.models._base import ModelResponse, ToolCall
from codeminions.testing import MockEnvironment, MockModel, run_blueprint_test

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples"

# Acceptance command used in example 09
ACCEPTANCE = "uv run pytest -q tests/test_core.py -k ConfigurationResolution"

# Realistic token costs for a coding task
_IMPL_TOKENS = dict(input_tokens=6_000, output_tokens=800)
_FIX_TOKENS = dict(input_tokens=4_000, output_tokens=600)
_JUDGE_APPROVE_TOKENS = dict(input_tokens=2_000, output_tokens=20)
_JUDGE_VETO_TOKENS = dict(input_tokens=2_000, output_tokens=60)


def _load_blueprint():
    ns = runpy.run_path(str(EXAMPLES_DIR / "validation" / "09_real_repo_config_resolution.py"))
    return ns["repo_spec_blueprint"]


def _base_env(acceptance_exit: int = 0) -> MockEnvironment:
    return MockEnvironment(
        exec_results={
            "git branch --show-current": "codeminions-real-audit",
            ACCEPTANCE: acceptance_exit,
            "git diff": "",
        }
    )


# ---------------------------------------------------------------------------
# Scenario 1: Happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_happy_path() -> None:
    """Acceptance passes first time: implement → verify (pass) → fix_acceptance skipped."""
    blueprint = _load_blueprint()

    result = await run_blueprint_test(
        blueprint=blueprint,
        task=Task(description="Implement config resolution", acceptance=ACCEPTANCE),
        model=MockModel(responses=[
            ModelResponse(
                tool_calls=[ToolCall("done", {"summary": "impl", "files_changed": ["src/codeminions/core/minion.py"]})],
                **_IMPL_TOKENS,
            ),
        ]),
        env=_base_env(acceptance_exit=0),
    )

    result.assert_passed()
    result.assert_node_ran("implement")
    result.assert_node_ran("verify")
    result.assert_node_skipped("fix_acceptance")
    assert result.state.acceptance_passed is True
    assert result.state.branch == "codeminions-real-audit"

    # Token budget: single implement round
    result.assert_tokens_under(10_000)

    # Tool call audit
    done_calls = result.trace.tool_calls("done")
    assert len(done_calls) == 1, "implement should call done() exactly once"


# ---------------------------------------------------------------------------
# Scenario 2: Acceptance fails, fix_acceptance runs once and completes
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_fix_acceptance_path() -> None:
    """Acceptance fails → fix_acceptance runs → blueprint completes."""
    blueprint = _load_blueprint()

    result = await run_blueprint_test(
        blueprint=blueprint,
        task=Task(description="Implement config resolution", acceptance=ACCEPTANCE),
        model=MockModel(responses=[
            ModelResponse(
                tool_calls=[ToolCall("done", {"summary": "partial", "files_changed": []})],
                **_IMPL_TOKENS,
            ),
            ModelResponse(
                tool_calls=[ToolCall("done", {"summary": "fixed", "files_changed": ["src/codeminions/core/minion.py"]})],
                **_FIX_TOKENS,
            ),
        ]),
        env=_base_env(acceptance_exit=1),
    )

    result.assert_passed()
    result.assert_node_ran("implement")
    result.assert_node_ran("fix_acceptance")

    # Both nodes ran: combined token budget
    result.assert_tokens_under(15_000)

    done_calls = result.trace.tool_calls("done")
    assert len(done_calls) == 2, "implement + fix_acceptance each call done() once"


# ---------------------------------------------------------------------------
# Scenario 3: Multi-tool implement (realistic tool call pattern)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_multi_tool_implement() -> None:
    """Agent uses several tools before done(). Verify trace tool_calls accounting."""
    blueprint = _load_blueprint()

    result = await run_blueprint_test(
        blueprint=blueprint,
        task=Task(description="Implement config resolution", acceptance=ACCEPTANCE),
        model=MockModel(responses=[
            ModelResponse(
                tool_calls=[
                    ToolCall("read_file", {"path": "src/codeminions/core/minion.py"}),
                    ToolCall("read_file", {"path": "tests/test_core.py"}),
                    ToolCall("write_file", {"path": "src/codeminions/core/minion.py", "content": "# updated"}),
                    ToolCall("run_command", {"cmd": "uv run pytest -q tests/test_core.py -k ConfigurationResolution"}),
                    ToolCall("done", {"summary": "impl", "files_changed": ["src/codeminions/core/minion.py"]}),
                ],
                **_IMPL_TOKENS,
            ),
        ]),
        env=MockEnvironment(
            exec_results={
                "git branch --show-current": "codeminions-real-audit",
                ACCEPTANCE: 0,
                "git diff": "",
                "uv run pytest -q tests/test_core.py -k ConfigurationResolution": 0,
            }
        ),
    )

    result.assert_passed()

    # Trace accounting: verify specific tool call counts
    reads = result.trace.tool_calls("read_file")
    writes = result.trace.tool_calls("write_file")
    assert len(reads) == 2
    assert len(writes) == 1

    # done() called exactly once
    assert len(result.trace.tool_calls("done")) == 1

    # Total tool calls from implement node
    impl_calls = result.trace.by_node("implement")
    tool_invocations = [e for e in impl_calls if e.type == "tool_call"]
    assert len(tool_invocations) == 5


# ---------------------------------------------------------------------------
# Scenario 4: Escalation path (fix_acceptance hits max_rounds)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_escalation_path() -> None:
    """implement runs + verify fails + fix_acceptance exhausts max_rounds → escalates."""
    blueprint = _load_blueprint()

    # fix_acceptance has max_rounds=2. After 2 rounds, the 3rd attempt escalates.
    # In this blueprint, fix_acceptance only runs once per blueprint execution
    # (it's a conditional node, not re-entered by a judge). max_rounds guards
    # against unexpected re-entry. We verify escalation via exhausted budget.
    #
    # To trigger escalation here: MockModel returns no done() — agent exhausts
    # iterations. Set max_iterations=1 in a patched blueprint variant.
    # Instead, we verify the escalation contract via a blueprint that
    # overrides on_max_rounds by using a direct engine test.

    # For the standard blueprint: verify that passing max_rounds=1 would escalate.
    # We parametrize this by loading the blueprint and confirming escalation when
    # the fix_acceptance node runs but the agent never calls done() (MockExhaustedError
    # → BlueprintEngine catches → escalation).
    #
    # Simplest approach: let MockModel exhaust before done() is called.
    from codeminions.testing.mock_model import MockExhaustedError

    result = await run_blueprint_test(
        blueprint=blueprint,
        task=Task(description="Implement config resolution", acceptance=ACCEPTANCE),
        model=MockModel(responses=[
            # implement: calls done()
            ModelResponse(
                tool_calls=[ToolCall("done", {"summary": "impl", "files_changed": []})],
                **_IMPL_TOKENS,
            ),
            # fix_acceptance: MockModel has no more responses → MockExhaustedError
            # → agent loop raises → BlueprintEngine escalates
        ]),
        env=_base_env(acceptance_exit=1),
    )

    # MockExhaustedError in fix_acceptance node causes escalation
    assert result.outcome == "escalated"
    assert isinstance(result, EscalationResult)
    assert result.node == "fix_acceptance"


# ---------------------------------------------------------------------------
# Scenario 5: Metrics summary (informational — never fails on its own)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_audit_metrics_summary(capsys) -> None:
    """Print a human-readable metrics table across key scenarios."""
    blueprint = _load_blueprint()
    task = Task(description="Implement config resolution", acceptance=ACCEPTANCE)

    scenarios: list[tuple[str, MockModel, MockEnvironment]] = [
        (
            "happy_path",
            MockModel(responses=[
                ModelResponse(
                    tool_calls=[ToolCall("done", {"summary": "impl", "files_changed": []})],
                    **_IMPL_TOKENS,
                )
            ]),
            _base_env(0),
        ),
        (
            "fix_acceptance",
            MockModel(responses=[
                ModelResponse(
                    tool_calls=[ToolCall("done", {"summary": "p1", "files_changed": []})],
                    **_IMPL_TOKENS,
                ),
                ModelResponse(
                    tool_calls=[ToolCall("done", {"summary": "p2", "files_changed": []})],
                    **_FIX_TOKENS,
                ),
            ]),
            _base_env(1),
        ),
    ]

    print("\n--- Reliability Audit: example 09 blueprint ---")
    print(f"{'Scenario':<25} {'Outcome':<12} {'Tokens':>8}  {'tool_calls':>10}  {'Nodes ran'}")
    print("-" * 80)

    for name, model, env in scenarios:
        result = await run_blueprint_test(blueprint=blueprint, task=task, model=model, env=env)
        nodes_ran = [e.node for e in result.trace.by_type("node_start")]
        n_tools = len(result.trace.tool_calls())
        print(
            f"{name:<25} {result.outcome:<12} {result.tokens:>8}  {n_tools:>10}  "
            f"{', '.join(nodes_ran)}"
        )

    print("-" * 80)

    captured = capsys.readouterr()
    assert "happy_path" in captured.out
    assert "fix_acceptance" in captured.out
