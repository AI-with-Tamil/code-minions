"""Tests for core SDK contracts: Task, Blueprint validation, tool decorator, environments."""

import pytest

from pydantic import BaseModel

from codeminions import (
    AgentNode,
    Blueprint,
    BlueprintValidationError,
    DeterministicNode,
    JudgeNode,
    LoopNode,
    Minion,
    ParallelNode,
    RunContext,
    Task,
    tool,
    ToolDefinitionError,
)
from codeminions.core.context import ExecResult
from codeminions.models._base import ModelResponse, ToolCall
from codeminions.testing import MockEnvironment, MockModel, run_blueprint_test


# --- Task ---

class TestTask:
    def test_string_coercion(self):
        t = Task.model_validate("Fix the bug")
        assert t.description == "Fix the bug"
        assert t.context == []
        assert t.acceptance == ""
        assert t.constraints == []

    def test_structured(self):
        t = Task(
            description="Add feature",
            context=["src/app.py"],
            acceptance="pytest passes",
            constraints=["No DB changes"],
            metadata={"ticket": "JIRA-123"},
        )
        assert t.metadata["ticket"] == "JIRA-123"
        assert "No DB changes" in t.constraints_list
        assert "src/app.py" in t.context_list

    def test_immutable(self):
        t = Task(description="test")
        with pytest.raises(Exception):
            t.description = "changed"


# --- Tool ---

class TestTool:
    def test_valid_sync_tool(self):
        @tool(description="Test")
        def my_tool(ctx: RunContext, name: str) -> str:
            return name

        assert my_tool.name == "my_tool"
        assert not my_tool.is_async

    def test_valid_async_tool(self):
        @tool(description="Test")
        async def my_tool(ctx: RunContext, name: str) -> str:
            return name

        assert my_tool.is_async

    def test_missing_ctx_raises(self):
        with pytest.raises(ToolDefinitionError, match="first parameter must be 'ctx"):
            @tool(description="Bad")
            def bad(name: str) -> str:
                return name

    def test_kwargs_raises(self):
        with pytest.raises(ToolDefinitionError, match="kwargs"):
            @tool(description="Bad")
            def bad(ctx: RunContext, **kwargs: str) -> str:
                return ""

    def test_untyped_param_raises(self):
        with pytest.raises(ToolDefinitionError, match="type annotation"):
            @tool(description="Bad")
            def bad(ctx: RunContext, name) -> str:
                return name

    def test_no_return_type_raises(self):
        with pytest.raises(ToolDefinitionError, match="return type"):
            @tool(description="Bad")
            def bad(ctx: RunContext, name: str):
                return name

    def test_schema_generation(self):
        @tool(description="Search")
        async def search(ctx: RunContext, query: str, limit: int = 10) -> list[str]:
            return []

        schema = search.schema()
        assert schema["name"] == "search"
        assert schema["input_schema"]["required"] == ["query"]
        assert schema["input_schema"]["properties"]["limit"]["default"] == 10


# --- Blueprint validation ---

class TestBlueprintValidation:
    def test_duplicate_names(self):
        bp = Blueprint(
            name="bad",
            nodes=[
                DeterministicNode("step", fn=lambda ctx: None),
                DeterministicNode("step", fn=lambda ctx: None),
            ],
        )
        with pytest.raises(BlueprintValidationError, match="duplicate"):
            bp.validate()

    def test_judge_references_missing_agent(self):
        bp = Blueprint(
            name="bad",
            nodes=[
                JudgeNode(name="judge", evaluates="ghost", criteria="check"),
            ],
        )
        with pytest.raises(BlueprintValidationError, match="ghost"):
            bp.validate()

    def test_judge_references_existing_agent(self):
        bp = Blueprint(
            name="good",
            nodes=[
                AgentNode("impl", system_prompt="do it", tools=[], max_rounds=2),
                JudgeNode(name="judge", evaluates="impl", criteria="check"),
            ],
        )
        bp.validate()  # should not raise

    def test_max_rounds_validation(self):
        bp = Blueprint(
            name="bad",
            nodes=[
                AgentNode("impl", system_prompt="x", tools=[], max_rounds=0),
            ],
        )
        with pytest.raises(BlueprintValidationError, match="max_rounds"):
            bp.validate()

    def test_state_cls_requires_defaults(self):
        class BadState(BaseModel):
            name: str  # no default!

        bp = Blueprint(name="bad", state_cls=BadState, nodes=[])
        with pytest.raises(BlueprintValidationError, match="no default"):
            bp.validate()


# --- Blueprint composition ---

class TestBlueprintComposition:
    def _base(self):
        return Blueprint(
            name="base",
            nodes=[
                DeterministicNode("a", fn=lambda ctx: None),
                DeterministicNode("b", fn=lambda ctx: None),
                DeterministicNode("c", fn=lambda ctx: None),
            ],
        )

    def test_add(self):
        bp1 = Blueprint(name="first", nodes=[DeterministicNode("x", fn=lambda ctx: None)])
        bp2 = Blueprint(name="second", nodes=[DeterministicNode("y", fn=lambda ctx: None)])
        combined = bp1 + bp2
        assert [n.name for n in combined.nodes] == ["x", "y"]

    def test_before(self):
        bp = self._base().before("b", DeterministicNode("new", fn=lambda ctx: None))
        assert [n.name for n in bp.nodes] == ["a", "new", "b", "c"]

    def test_after(self):
        bp = self._base().after("b", DeterministicNode("new", fn=lambda ctx: None))
        assert [n.name for n in bp.nodes] == ["a", "b", "new", "c"]

    def test_replace(self):
        bp = self._base().replace("b", DeterministicNode("b", fn=lambda ctx: None))
        assert [n.name for n in bp.nodes] == ["a", "b", "c"]

    def test_without(self):
        bp = self._base().without("b")
        assert [n.name for n in bp.nodes] == ["a", "c"]

    def test_without_nonexistent_raises(self):
        with pytest.raises(ValueError, match="ghost"):
            self._base().without("ghost")


# --- ExecResult ---

class TestExecResult:
    def test_ok_property(self):
        assert ExecResult(stdout="", stderr="", exit_code=0).ok is True
        assert ExecResult(stdout="", stderr="", exit_code=1).ok is False


# --- MockEnvironment ---

class TestMockEnvironment:
    @pytest.mark.asyncio
    async def test_read_write(self):
        env = MockEnvironment(files={"a.py": "hello"})
        assert await env.read("a.py") == "hello"
        await env.write("b.py", "world")
        assert await env.read("b.py") == "world"

    @pytest.mark.asyncio
    async def test_read_missing_raises(self):
        env = MockEnvironment()
        with pytest.raises(FileNotFoundError):
            await env.read("nope.py")

    @pytest.mark.asyncio
    async def test_edit(self):
        env = MockEnvironment(files={"a.py": "foo bar"})
        await env.edit("a.py", "foo", "baz")
        assert env.files["a.py"] == "baz bar"

    @pytest.mark.asyncio
    async def test_exec_exact_match(self):
        env = MockEnvironment(exec_results={"ls": 0})
        result = await env.exec("ls")
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_exec_glob_match(self):
        env = MockEnvironment(exec_results={"git checkout -b *": 0})
        result = await env.exec("git checkout -b codeminions/abc")
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_exec_string_result(self):
        env = MockEnvironment(exec_results={"echo hi": "hi\n"})
        result = await env.exec("echo hi")
        assert result.stdout == "hi\n"
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_glob(self):
        env = MockEnvironment(files={"src/a.py": "", "src/b.py": "", "test.txt": ""})
        matches = await env.glob("src/*.py")
        assert matches == ["src/a.py", "src/b.py"]

    @pytest.mark.asyncio
    async def test_calls_recorded(self):
        env = MockEnvironment(files={"a.py": "x"})
        await env.read("a.py")
        await env.write("b.py", "y")
        assert len(env.calls) == 2


class TestMinionConfigurationResolution:
    def test_partial_minion_toml_falls_back_to_pyproject_per_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path,
    ) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.codeminions]\n"
            'model = "from-pyproject-model"\n'
            'blueprint = "from-pyproject-blueprint"\n'
            'environment = "from-pyproject-environment"\n',
            encoding="utf-8",
        )
        (tmp_path / "codeminions.toml").write_text(
            "[codeminions]\n"
            'model = "from-codeminions-model"\n',
            encoding="utf-8",
        )

        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CODEMINIONS_MODEL", raising=False)
        monkeypatch.delenv("CODEMINIONS_BLUEPRINT", raising=False)
        monkeypatch.delenv("CODEMINIONS_ENVIRONMENT", raising=False)

        minion = Minion()

        assert minion._model_spec == "from-codeminions-model"
        assert minion._blueprint_spec == "from-pyproject-blueprint"
        assert minion._environment_spec == "from-pyproject-environment"


# --- RunResult assertions ---

class TestRunResultAssertions:
    @pytest.mark.asyncio
    async def test_assert_methods(self):
        """Verify RunResult assertion methods work."""

        class S(BaseModel):
            branch: str = ""

        model = MockModel(responses=[
            ModelResponse(tool_calls=[
                ToolCall("done", {"summary": "Done", "files_changed": []}),
            ]),
        ])
        env = MockEnvironment()

        bp = Blueprint(
            name="simple",
            state_cls=S,
            nodes=[
                DeterministicNode("setup", fn=lambda ctx: None),
                AgentNode("work", system_prompt="do it", tools=[]),
            ],
        )

        result = await run_blueprint_test(bp, "test task", model, env)
        result.assert_passed()
        result.assert_node_ran("setup")
        result.assert_node_ran("work")

        with pytest.raises(AssertionError):
            result.assert_failed()
        with pytest.raises(AssertionError):
            result.assert_node_skipped("setup")


def test_agent_max_rounds_validates_for_judge_retry():
    """Judge retry requires the target AgentNode to be re-enterable."""

    class S(BaseModel):
        branch: str = ""

    bp = Blueprint(
        name="judge_retry_limit",
        state_cls=S,
        nodes=[
            AgentNode(
                "implement",
                system_prompt="Do it",
                tools=[],
                max_rounds=1,
                on_max_rounds="escalate",
            ),
            JudgeNode(
                name="review",
                evaluates="implement",
                criteria="Be correct",
                on_veto="retry",
                max_vetoes=2,
            ),
        ],
    )

    with pytest.raises(BlueprintValidationError, match="max_rounds >= 2"):
        bp.validate()


@pytest.mark.asyncio
async def test_token_accounting_includes_ctx_ask():
    """One-shot ctx.ask() calls should contribute to total tokens."""

    class S(BaseModel):
        answer: str = ""

    async def ask_once(ctx: RunContext) -> None:
        ctx.state.answer = await ctx.ask("hello", max_tokens=32)

    model = MockModel(responses=[
        ModelResponse(text="world", input_tokens=11, output_tokens=5),
    ])

    bp = Blueprint(
        name="ask_tokens",
        state_cls=S,
        nodes=[DeterministicNode("ask", fn=ask_once)],
    )

    result = await run_blueprint_test(bp, "test task", model, MockEnvironment())
    result.assert_passed()
    assert result.tokens == 16
    assert result.state.answer == "world"


@pytest.mark.asyncio
async def test_run_stream_yields_trace_events_live():
    """run_stream should yield events, not replay only after completion."""

    class S(BaseModel):
        branch: str = ""

    model = MockModel(responses=[
        ModelResponse(tool_calls=[
            ToolCall("done", {"summary": "Done", "files_changed": []}),
        ]),
    ])

    bp = Blueprint(
        name="streaming",
        state_cls=S,
        nodes=[AgentNode("implement", system_prompt="do it", tools=[])],
    )

    minion = Minion(model=model, blueprint=bp, environment=MockEnvironment())
    events = []
    async for event in minion.run_stream("test task"):
        events.append(event)

    assert any(event["type"] == "node_start" and event["node"] == "implement" for event in events)
    assert any(event["type"] == "agent_done" and event["node"] == "implement" for event in events)


@pytest.mark.asyncio
async def test_run_captures_diff_before_cleanup():
    """Diff should be captured before environment cleanup destroys access."""

    class DiffEnv(MockEnvironment):
        def __init__(self) -> None:
            super().__init__(exec_results={"git diff": "diff --git a/x b/x"})
            self.cleaned = False

        async def exec(self, cmd: str, cwd: str | None = None) -> ExecResult:
            if cmd == "git diff" and self.cleaned:
                raise RuntimeError("environment already cleaned")
            return await super().exec(cmd, cwd=cwd)

        async def cleanup(self) -> None:
            self.cleaned = True
            await super().cleanup()

    class S(BaseModel):
        branch: str = ""

    model = MockModel(responses=[
        ModelResponse(tool_calls=[
            ToolCall("done", {"summary": "Done", "files_changed": []}),
        ]),
    ])

    bp = Blueprint(
        name="diff_capture",
        state_cls=S,
        nodes=[AgentNode("implement", system_prompt="do it", tools=[])],
    )

    result = await Minion(model=model, blueprint=bp, environment=DiffEnv()).run("task")
    assert "diff --git" in result.diff


# --- LoopNode ---

@pytest.mark.asyncio
async def test_loop_node():
    """LoopNode iterates sub-blueprint over targets."""

    class MState(BaseModel):
        targets: list[str] = []
        current: str = ""
        processed: list[str] = []

    async def discover(ctx: RunContext) -> None:
        ctx.state.targets = ["a.py", "b.py"]

    async def record(ctx: RunContext) -> None:
        ctx.state.processed.append(ctx.state.current)

    sub = Blueprint(
        name="per_item",
        nodes=[
            DeterministicNode("process", fn=record),
        ],
    )

    bp = Blueprint(
        name="loop_test",
        state_cls=MState,
        nodes=[
            DeterministicNode("discover", fn=discover),
            LoopNode(
                "loop",
                sub_blueprint=sub,
                iterate_over=lambda ctx: ctx.state.targets,
                bind=lambda ctx, item: setattr(ctx.state, "current", item),
            ),
        ],
    )

    result = await run_blueprint_test(bp, "test", MockModel(), MockEnvironment())
    result.assert_passed()
    assert result.state.processed == ["a.py", "b.py"]


@pytest.mark.asyncio
async def test_loop_node_with_agent_resets_rounds():
    """LoopNode resets agent round counters per iteration.

    Matches Example 03 (Airbnb migration): AgentNode with max_rounds=3 inside
    a LoopNode should get fresh rounds budget per target file, not exhaust
    rounds across all files.
    """

    class MState(BaseModel):
        targets: list[str] = []
        current: str = ""
        migrated: list[str] = []

    async def discover(ctx: RunContext) -> None:
        ctx.state.targets = ["a.py", "b.py", "c.py", "d.py"]

    async def record(ctx: RunContext) -> None:
        ctx.state.migrated.append(ctx.state.current)

    sub = Blueprint(
        name="per_file",
        nodes=[
            AgentNode(
                "migrate",
                system_prompt="Migrate the file. Call done() when finished.",
                tools=[],
                max_iterations=10,
                token_budget=5_000,
                max_rounds=2,
                on_max_rounds="continue",
            ),
            DeterministicNode("validate", fn=record),
        ],
    )

    bp = Blueprint(
        name="loop_rounds_test",
        state_cls=MState,
        nodes=[
            DeterministicNode("discover", fn=discover),
            LoopNode(
                "loop",
                sub_blueprint=sub,
                iterate_over=lambda ctx: ctx.state.targets,
                bind=lambda ctx, item: setattr(ctx.state, "current", item),
                on_failure="continue",
            ),
        ],
    )

    # Each file needs one agent call that calls done(). 4 files = 4 responses.
    result = await run_blueprint_test(
        bp, "Migrate all files",
        MockModel(responses=[
            ModelResponse(tool_calls=[ToolCall("done", {"summary": "Migrated a.py", "files_changed": ["a.py"]})]),
            ModelResponse(tool_calls=[ToolCall("done", {"summary": "Migrated b.py", "files_changed": ["b.py"]})]),
            ModelResponse(tool_calls=[ToolCall("done", {"summary": "Migrated c.py", "files_changed": ["c.py"]})]),
            ModelResponse(tool_calls=[ToolCall("done", {"summary": "Migrated d.py", "files_changed": ["d.py"]})]),
        ]),
        MockEnvironment(),
    )

    result.assert_passed()
    # All 4 files should be migrated — rounds reset per iteration
    assert result.state.migrated == ["a.py", "b.py", "c.py", "d.py"]


# --- ParallelNode ---

@pytest.mark.asyncio
async def test_parallel_node():
    """ParallelNode runs children concurrently."""

    class PState(BaseModel):
        a_ran: bool = False
        b_ran: bool = False

    async def set_a(ctx: RunContext) -> None:
        ctx.state.a_ran = True

    async def set_b(ctx: RunContext) -> None:
        ctx.state.b_ran = True

    bp = Blueprint(
        name="parallel_test",
        state_cls=PState,
        nodes=[
            ParallelNode(
                "parallel",
                nodes=[
                    DeterministicNode("a", fn=set_a),
                    DeterministicNode("b", fn=set_b),
                ],
            ),
        ],
    )

    result = await run_blueprint_test(bp, "test", MockModel(), MockEnvironment())
    result.assert_passed()
    assert result.state.a_ran is True
    assert result.state.b_ran is True


# --- Conditional nodes ---

@pytest.mark.asyncio
async def test_condition_skip():
    """Nodes with condition=False are skipped."""

    class S(BaseModel):
        flag: bool = False

    async def noop(ctx: RunContext) -> None:
        pass

    bp = Blueprint(
        name="cond_test",
        state_cls=S,
        nodes=[
            DeterministicNode("always", fn=noop),
            DeterministicNode("conditional", fn=noop, condition=lambda ctx: ctx.state.flag),
        ],
    )

    result = await run_blueprint_test(bp, "test", MockModel(), MockEnvironment())
    result.assert_passed()
    result.assert_node_ran("always")
    result.assert_node_skipped("conditional")


# --- Trace query helpers ---

class TestTraceQueryHelpers:
    def test_by_type_filters_correctly(self) -> None:
        from codeminions.trace import Trace

        t = Trace(run_id="r1")
        t.record_node_start("a")
        t.record_node_start("b")
        t.record_skip("c")
        t.record_tool_call("a", "read_file", {"path": "x.py"})

        starts = t.by_type("node_start")
        assert len(starts) == 2
        assert all(e.type == "node_start" for e in starts)

        skips = t.by_type("node_skip")
        assert len(skips) == 1 and skips[0].node == "c"

    def test_by_node_filters_correctly(self) -> None:
        from codeminions.trace import Trace

        t = Trace(run_id="r2")
        t.record_node_start("alpha")
        t.record_tool_call("alpha", "write_file", {"path": "a.py", "content": "x"})
        t.record_node_start("beta")
        t.record_tool_call("beta", "run_command", {"cmd": "ls"})

        alpha_events = t.by_node("alpha")
        assert all(e.node == "alpha" for e in alpha_events)
        assert {e.type for e in alpha_events} == {"node_start", "tool_call"}

        beta_events = t.by_node("beta")
        assert len(beta_events) == 2

    def test_tool_calls_returns_all_when_no_filter(self) -> None:
        from codeminions.trace import Trace

        t = Trace(run_id="r3")
        t.record_tool_call("n1", "read_file", {"path": "a.py"})
        t.record_tool_call("n1", "write_file", {"path": "b.py", "content": ""})
        t.record_skip("n2")

        calls = t.tool_calls()
        assert len(calls) == 2
        assert all(e.type == "tool_call" for e in calls)

    def test_tool_calls_filters_by_name(self) -> None:
        from codeminions.trace import Trace

        t = Trace(run_id="r4")
        t.record_tool_call("n", "read_file", {"path": "a.py"})
        t.record_tool_call("n", "write_file", {"path": "b.py", "content": ""})
        t.record_tool_call("n", "read_file", {"path": "c.py"})

        reads = t.tool_calls("read_file")
        assert len(reads) == 2
        assert all(e.data["tool"] == "read_file" for e in reads)

        writes = t.tool_calls("write_file")
        assert len(writes) == 1

    def test_tool_calls_empty_when_none_recorded(self) -> None:
        from codeminions.trace import Trace

        t = Trace(run_id="r5")
        t.record_node_start("n")
        assert t.tool_calls() == []
        assert t.tool_calls("missing") == []


# --- RunResult judge assertions ---

import pytest
from codeminions.testing import MockModel, MockEnvironment, run_blueprint_test
from codeminions.models._base import ModelResponse, ToolCall as TC


@pytest.mark.asyncio
async def test_judge_approved_assertion() -> None:
    """assert_judge_approved passes when judge approves."""
    from codeminions import Blueprint, AgentNode, JudgeNode
    from pydantic import BaseModel

    class S(BaseModel):
        verdict: str = ""

    bp = Blueprint(
        name="judge_approve_test",
        state_cls=S,
        nodes=[
            AgentNode("impl", system_prompt="Implement", tools=[], max_rounds=2),
            JudgeNode("judge", evaluates="impl", criteria="Is it good?", on_veto="escalate"),
        ],
    )

    result = await run_blueprint_test(
        bp,
        "task",
        model=MockModel(responses=[
            ModelResponse(tool_calls=[TC("done", {"summary": "done", "files_changed": []})]),
            ModelResponse(text="APPROVE", input_tokens=5, output_tokens=2),
        ]),
        env=MockEnvironment(exec_results={"git diff": ""}),
    )

    result.assert_passed()
    result.assert_judge_approved("judge")
    verdicts = result.judge_verdicts()
    assert verdicts == {"judge": "approved"}


@pytest.mark.asyncio
async def test_judge_vetoed_assertion() -> None:
    """assert_judge_vetoed passes when judge vetoes; judge_verdicts reflects final outcome."""
    from codeminions import Blueprint, AgentNode, JudgeNode
    from pydantic import BaseModel

    class S(BaseModel):
        verdict: str = ""

    bp = Blueprint(
        name="judge_veto_test",
        state_cls=S,
        nodes=[
            AgentNode("impl", system_prompt="Implement", tools=[], max_rounds=3),
            JudgeNode("judge", evaluates="impl", criteria="Is it good?",
                      max_vetoes=2, on_veto="retry"),
        ],
    )

    result = await run_blueprint_test(
        bp,
        "task",
        model=MockModel(responses=[
            # initial impl
            ModelResponse(tool_calls=[TC("done", {"summary": "first", "files_changed": []})]),
            # judge vetoes
            ModelResponse(text="VETO: too broad", input_tokens=5, output_tokens=4),
            # retry impl
            ModelResponse(tool_calls=[TC("done", {"summary": "narrower", "files_changed": []})]),
            # judge approves
            ModelResponse(text="APPROVE", input_tokens=5, output_tokens=2),
        ]),
        env=MockEnvironment(exec_results={"git diff": ""}),
    )

    result.assert_passed()
    result.assert_judge_vetoed("judge")
    result.assert_judge_vetoed("judge", reason="too broad")
    result.assert_judge_approved("judge")
    verdicts = result.judge_verdicts()
    assert verdicts == {"judge": "approved"}  # last event wins


@pytest.mark.asyncio
async def test_judge_verdicts_with_no_judge() -> None:
    """judge_verdicts returns empty dict when no judge ran."""
    from codeminions import Blueprint, DeterministicNode
    from pydantic import BaseModel

    async def noop(ctx: RunContext) -> None:
        pass

    bp = Blueprint(name="no_judge", nodes=[DeterministicNode("n", fn=noop)])
    result = await run_blueprint_test(bp, "t", MockModel(), MockEnvironment())
    assert result.judge_verdicts() == {}
