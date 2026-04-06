"""Test Example 01 — Stripe pattern end-to-end with mocks."""

import pytest

from minion import (
    AgentNode,
    Blueprint,
    DeterministicNode,
    EscalationResult,
    RunContext,
)
from minion.tools import CODE_TOOLS, SHELL_TOOLS
from minion.models._base import ModelResponse, ToolCall
from minion.testing import MockEnvironment, MockModel, run_blueprint_test
from pydantic import BaseModel


# Replicate the Example 01 blueprint structure for testing
class CodingState(BaseModel):
    branch: str = ""
    context_summary: str = ""
    lint_failed: bool = False
    lint_output: str = ""
    tests_failed: bool = False
    test_output: str = ""
    files_changed: list[str] = []
    pr_url: str = ""


async def create_branch(ctx: RunContext) -> None:
    ctx.state.branch = f"minion/{ctx.run_id[:8]}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")


async def gather_context(ctx: RunContext) -> None:
    result = await ctx.exec("git log --oneline -10")
    ctx.state.context_summary = result.stdout


async def run_lint(ctx: RunContext) -> None:
    result = await ctx.exec("ruff check . --fix")
    ctx.state.lint_failed = result.exit_code != 0
    ctx.state.lint_output = result.stdout


async def run_tests(ctx: RunContext) -> None:
    await ctx.exec("pytest tests/ --snapshot-update -q")
    result = await ctx.exec("pytest tests/ -x --tb=short")
    ctx.state.tests_failed = result.exit_code != 0
    ctx.state.test_output = result.stdout


async def commit_changes(ctx: RunContext) -> None:
    await ctx.exec("git add -A")
    await ctx.exec('git commit -m "minion: complete task"')


async def push_branch(ctx: RunContext) -> None:
    await ctx.exec(f"git push -u origin {ctx.state.branch}")


async def create_pr(ctx: RunContext) -> None:
    result = await ctx.exec(
        f'gh pr create --title "minion: {ctx.task.description[:72]}" '
        f'--body "Automated by Minion SDK\n\nTask: {ctx.task.description}" '
        f'--head {ctx.state.branch}'
    )
    ctx.state.pr_url = result.stdout.strip()


test_blueprint = Blueprint(
    name="coding",
    state_cls=CodingState,
    nodes=[
        DeterministicNode("create_branch", fn=create_branch),
        DeterministicNode("gather_context", fn=gather_context),
        AgentNode(
            "implement",
            system_prompt="Complete the task. Call done() when finished.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            max_iterations=80,
            token_budget=60_000,
        ),
        DeterministicNode("lint", fn=run_lint),
        AgentNode(
            "fix_lint",
            system_prompt="Fix lint errors.",
            tools=CODE_TOOLS,
            condition=lambda ctx: ctx.state.lint_failed,
            max_iterations=20,
            token_budget=15_000,
            max_rounds=1,
        ),
        DeterministicNode("test", fn=run_tests),
        AgentNode(
            "fix_tests",
            system_prompt="Fix failing tests.",
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: ctx.state.tests_failed,
            max_iterations=40,
            token_budget=30_000,
            max_rounds=2,
            on_max_rounds="escalate",
        ),
        DeterministicNode("commit", fn=commit_changes),
        DeterministicNode("push", fn=push_branch),
        DeterministicNode("create_pr", fn=create_pr),
    ],
)


@pytest.mark.asyncio
async def test_stripe_happy_path():
    """Full happy path: all deterministic nodes run, fix_lint and fix_tests skipped."""
    model = MockModel(responses=[
        # implement: read → edit → done
        ModelResponse(tool_calls=[
            ToolCall("read_file", {"path": "src/signup.py"}),
        ]),
        ModelResponse(tool_calls=[
            ToolCall("edit_file", {
                "path": "src/signup.py",
                "old": "def signup(data):\n    pass",
                "new": "def signup(data):\n    if not data.get('email'):\n        raise ValueError('email required')\n    pass",
            }),
        ]),
        ModelResponse(tool_calls=[
            ToolCall("done", {
                "summary": "Added email validation to signup endpoint",
                "files_changed": ["src/signup.py"],
            }),
        ]),
    ])

    env = MockEnvironment(
        files={
            "src/signup.py": "def signup(data):\n    pass\n",
        },
        exec_results={
            "git checkout -b *": 0,
            "git log --oneline -10": "abc1234 initial commit",
            "ruff check . --fix": 0,
            "pytest tests/ --snapshot-update -q": 0,
            "pytest tests/ -x --tb=short": 0,
            "git add -A": 0,
            'git commit -m "minion: complete task"': 0,
            "git push -u origin *": 0,
            "gh pr create *": "https://github.com/org/repo/pull/42",
        },
    )

    result = await run_blueprint_test(
        blueprint=test_blueprint,
        task="Add input validation for missing email in the signup endpoint",
        model=model,
        env=env,
    )

    result.assert_passed()
    result.assert_node_ran("create_branch")
    result.assert_node_ran("gather_context")
    result.assert_node_ran("implement")
    result.assert_node_ran("lint")
    result.assert_node_skipped("fix_lint")
    result.assert_node_ran("test")
    result.assert_node_skipped("fix_tests")
    result.assert_node_ran("commit")
    result.assert_node_ran("push")
    result.assert_node_ran("create_pr")

    result.assert_tool_called("read_file", path="src/signup.py")
    result.assert_tool_called("edit_file", path="src/signup.py")

    assert result.state.branch.startswith("minion/")
    assert result.state.lint_failed is False
    assert result.state.tests_failed is False
    assert result.state.pr_url == "https://github.com/org/repo/pull/42"
    assert "email required" in env.files["src/signup.py"]


@pytest.mark.asyncio
async def test_stripe_lint_failure_triggers_fix():
    """Lint fails → fix_lint agent runs."""
    model = MockModel(responses=[
        # implement
        ModelResponse(tool_calls=[
            ToolCall("done", {"summary": "Implemented feature", "files_changed": ["src/app.py"]}),
        ]),
        # fix_lint (triggered by lint failure)
        ModelResponse(tool_calls=[
            ToolCall("done", {"summary": "Fixed lint errors", "files_changed": ["src/app.py"]}),
        ]),
    ])

    env = MockEnvironment(
        files={"src/app.py": "x = 1\n"},
        exec_results={
            "git checkout -b *": 0,
            "git log --oneline -10": "abc initial",
            "ruff check . --fix": 1,   # lint fails
            "pytest tests/ --snapshot-update -q": 0,
            "pytest tests/ -x --tb=short": 0,
            "git add -A": 0,
            'git commit -m "minion: complete task"': 0,
            "git push -u origin *": 0,
            "gh pr create *": "https://github.com/org/repo/pull/43",
        },
    )

    result = await run_blueprint_test(
        blueprint=test_blueprint,
        task="Add feature",
        model=model,
        env=env,
    )

    result.assert_passed()
    result.assert_node_ran("fix_lint")
    result.assert_node_skipped("fix_tests")
    assert result.state.lint_failed is True


@pytest.mark.asyncio
async def test_blueprint_validation():
    """Blueprint validates node names, judge references, etc."""
    from minion import Blueprint, JudgeNode

    bp = Blueprint(
        name="bad",
        nodes=[
            JudgeNode(name="judge", evaluates="nonexistent", criteria="test"),
        ],
    )
    with pytest.raises(Exception, match="nonexistent"):
        bp.validate()


@pytest.mark.asyncio
async def test_blueprint_composition():
    """Blueprint composition operators work correctly."""
    bp = test_blueprint

    # without
    no_pr = bp.without("create_pr")
    assert all(n.name != "create_pr" for n in no_pr.nodes)

    # before
    from minion import DeterministicNode
    async def security_scan(ctx: RunContext) -> None:
        pass
    extended = bp.before("push", DeterministicNode("security_scan", fn=security_scan))
    names = [n.name for n in extended.nodes]
    assert names.index("security_scan") < names.index("push")

    # after
    extended2 = bp.after("implement", DeterministicNode("format", fn=security_scan))
    names2 = [n.name for n in extended2.nodes]
    assert names2.index("format") == names2.index("implement") + 1

    # replace
    replaced = bp.replace("implement", DeterministicNode("implement", fn=security_scan))
    impl_node = [n for n in replaced.nodes if n.name == "implement"][0]
    assert isinstance(impl_node, DeterministicNode)


@pytest.mark.asyncio
async def test_task_structured():
    """Task accepts structured input and string shorthand."""
    from minion import Task

    # Structured
    t = Task(
        description="Fix bug",
        context=["src/app.py"],
        acceptance="pytest passes",
        constraints=["No DB changes"],
    )
    assert t.description == "Fix bug"
    assert t.context == ["src/app.py"]
    assert "No DB changes" in t.constraints_list

    # String shorthand
    t2 = Task.model_validate("Fix bug")
    assert t2.description == "Fix bug"
    assert t2.context == []


@pytest.mark.asyncio
async def test_tool_decorator():
    """@tool validates signatures and generates schemas."""
    from minion import tool, RunContext

    @tool(description="Test tool")
    async def my_tool(ctx: RunContext, name: str, count: int = 5) -> str:
        return f"{name}: {count}"

    assert my_tool.name == "my_tool"
    assert "name" in my_tool.parameters
    assert "count" in my_tool.parameters
    assert my_tool.required == ["name"]

    schema = my_tool.schema()
    assert schema["name"] == "my_tool"
    assert schema["input_schema"]["properties"]["name"]["type"] == "string"
    assert schema["input_schema"]["properties"]["count"]["default"] == 5
