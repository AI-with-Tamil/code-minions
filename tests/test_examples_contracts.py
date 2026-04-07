"""Contract tests for public examples and Minion config resolution."""

from __future__ import annotations

import runpy
from pathlib import Path

import pytest

from minion import Blueprint, Minion, Task
from minion.models._base import ModelResponse, ToolCall
from minion.testing import MockEnvironment, MockModel, run_blueprint_test


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_DIR = ROOT / "examples"


def _load_example(filename: str) -> dict[str, object]:
    return runpy.run_path(str(EXAMPLES_DIR / filename))


def _blueprints_from(namespace: dict[str, object]) -> list[Blueprint]:
    return [value for value in namespace.values() if isinstance(value, Blueprint)]


def test_public_examples_compile_and_validate() -> None:
    for filename in [
        "01_stripe_pattern.py",
        "02_spotify_judge.py",
        "03_airbnb_migration.py",
        "04_linkedin_spec.py",
        "05_anthropic_two_agent.py",
        "06_ramp_docker.py",
        "07_coinbase_council.py",
        "08_real_llm_smoke.py",
        "09_real_repo_config_resolution.py",
    ]:
        namespace = _load_example(filename)
        blueprints = _blueprints_from(namespace)
        assert blueprints, f"{filename} should expose at least one Blueprint"
        for blueprint in blueprints:
            blueprint.validate()


def test_minion_config_resolution_order(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        "[tool.minion]\n"
        'model = "from-pyproject"\n'
        'blueprint = "from-pyproject"\n'
        'environment = "from-pyproject"\n',
        encoding="utf-8",
    )
    (tmp_path / "minion.toml").write_text(
        "[minion]\n"
        'model = "from-minion"\n'
        'blueprint = "from-minion"\n'
        'environment = "from-minion"\n',
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MINION_MODEL", "from-env")
    monkeypatch.setenv("MINION_BLUEPRINT", "from-env")
    monkeypatch.setenv("MINION_ENVIRONMENT", "from-env")

    defaulted = Minion()
    assert defaulted._model_spec == "from-minion"
    assert defaulted._blueprint_spec == "from-minion"
    assert defaulted._environment_spec == "from-minion"

    overridden = Minion(
        model="from-constructor",
        blueprint="from-constructor",
        environment="from-constructor",
    )
    assert overridden._model_spec == "from-constructor"
    assert overridden._blueprint_spec == "from-constructor"
    assert overridden._environment_spec == "from-constructor"


@pytest.mark.asyncio
async def test_example_02_spotify_judge_retry_contract() -> None:
    ns = _load_example("02_spotify_judge.py")
    blueprint = ns["spotify_blueprint"]

    result = await run_blueprint_test(
        blueprint=blueprint,
        task="Add request ID header to all API responses",
        model=MockModel(
            responses=[
                ModelResponse(tool_calls=[ToolCall("done", {"summary": "Implemented request id", "files_changed": ["src/api.py"]})]),
                ModelResponse(text="VETO: scope creep", input_tokens=10, output_tokens=5),
                ModelResponse(tool_calls=[ToolCall("done", {"summary": "Retried narrowly", "files_changed": ["src/api.py"]})]),
                ModelResponse(text="APPROVE", input_tokens=10, output_tokens=2),
            ]
        ),
        env=MockEnvironment(
            exec_results={
                "ruff check . --fix": 0,
                "pytest tests/ -x --tb=short": 0,
                "gh pr create *": "https://example.test/pr/1",
            }
        ),
    )

    result.assert_passed()
    result.assert_node_ran("judge")
    result.assert_node_skipped("fix_lint")
    result.assert_node_skipped("fix_tests")


@pytest.mark.asyncio
async def test_example_03_airbnb_loop_contract() -> None:
    ns = _load_example("03_airbnb_migration.py")
    blueprint = ns["migration_blueprint"]

    result = await run_blueprint_test(
        blueprint=blueprint,
        task="Migrate all Enzyme tests to React Testing Library",
        model=MockModel(
            responses=[
                ModelResponse(tool_calls=[ToolCall("done", {"summary": "Migrated first file", "files_changed": ["tests/a_test.py"]})]),
                ModelResponse(tool_calls=[ToolCall("done", {"summary": "Migrated second file", "files_changed": ["tests/b_test.py"]})]),
            ]
        ),
        env=MockEnvironment(
            exec_results={
                "rg -l 'Enzyme\\|shallow\\|mount' tests/": "tests/a_test.py\ntests/b_test.py\n",
                "pytest tests/a_test.py --tb=short -q": 0,
                "pytest tests/b_test.py --tb=short -q": 0,
            }
        ),
    )

    result.assert_passed()
    assert result.state.migrated == ["tests/a_test.py", "tests/b_test.py"]
    assert result.state.failed == []


@pytest.mark.asyncio
async def test_example_04_linkedin_spec_contract() -> None:
    ns = _load_example("04_linkedin_spec.py")
    blueprint = ns["spec_blueprint"]

    task = Task(
        description="Add JWT refresh token rotation to the auth service",
        context=["src/auth/tokens.py", "tests/test_auth.py"],
        acceptance="pytest tests/test_auth.py -k 'refresh' -v",
        constraints=["Do not modify the database schema"],
    )

    result = await run_blueprint_test(
        blueprint=blueprint,
        task=task,
        model=MockModel(
            responses=[
                ModelResponse(tool_calls=[ToolCall("done", {"summary": "Implemented refresh rotation", "files_changed": ["src/auth/tokens.py"]})]),
                ModelResponse(text="APPROVE", input_tokens=10, output_tokens=2),
            ]
        ),
        env=MockEnvironment(
            exec_results={
                "pytest tests/test_auth.py -k 'refresh' -v": 0,
                "gh pr create *": "https://example.test/pr/2",
            }
        ),
    )

    result.assert_passed()
    assert result.state.acceptance_passed is True
    result.assert_node_skipped("fix_acceptance")


@pytest.mark.asyncio
async def test_example_05_two_agent_handoff_contract() -> None:
    ns = _load_example("05_anthropic_two_agent.py")
    blueprint = ns["two_agent_blueprint"]
    progress_file = ns["PROGRESS_FILE"]

    initial_progress = (
        '{\n'
        '  "features": [\n'
        '    {"id": "f1", "description": "Implement token storage", "status": "pending"}\n'
        '  ]\n'
        '}'
    )

    result = await run_blueprint_test(
        blueprint=blueprint,
        task="Implement OAuth2 login with Google and GitHub providers",
        model=MockModel(
            responses=[
                ModelResponse(
                    tool_calls=[
                        ToolCall("write_file", {"path": progress_file, "content": initial_progress}),
                        ToolCall("done", {"summary": "Initialized progress file", "files_changed": [progress_file]}),
                    ]
                ),
                ModelResponse(
                    tool_calls=[
                        ToolCall("done", {"summary": "Implemented feature f1", "files_changed": ["f1"]}),
                    ]
                ),
            ]
        ),
        env=MockEnvironment(
            exec_results={
                "git checkout -b *": 0,
                "git add -A": 0,
                "git commit -m *": 0,
            }
        ),
    )

    result.assert_passed()
    assert result.state.current_feature["id"] == "f1"
    result.assert_tool_called("write_file", path=progress_file)


@pytest.mark.asyncio
async def test_example_06_ramp_docker_contract() -> None:
    ns = _load_example("06_ramp_docker.py")
    blueprint = ns["ramp_blueprint"]

    result = await run_blueprint_test(
        blueprint=blueprint,
        task="Add Redis-based rate limiting to the payment processing endpoint",
        model=MockModel(
            responses=[
                ModelResponse(tool_calls=[ToolCall("done", {"summary": "Implemented rate limiting", "files_changed": ["src/payments.py"]})]),
            ]
        ),
        env=MockEnvironment(
            exec_results={
                "pg_ctlcluster 15 main start": 0,
                "redis-server --daemonize yes": 0,
                "python manage.py migrate --run-syncdb": 0,
                "pg_isready": 0,
                "redis-cli ping": "PONG",
                "pytest tests/integration/ -x --tb=short -q --database-url=postgresql://localhost/test_db": 0,
                "gh pr create *": "https://example.test/pr/3",
            }
        ),
    )

    result.assert_passed()
    assert result.state.services_ready is True
    result.assert_node_skipped("fix_integration")


@pytest.mark.asyncio
async def test_example_07_coinbase_council_contract() -> None:
    ns = _load_example("07_coinbase_council.py")
    blueprint = ns["council_blueprint"]

    result = await run_blueprint_test(
        blueprint=blueprint,
        task="Add transaction fee calculation with support for tiered pricing",
        model=MockModel(
            responses=[
                ModelResponse(tool_calls=[ToolCall("done", {"summary": "Implemented tiered pricing", "files_changed": ["src/fees.py"]})]),
                ModelResponse(text="APPROVE", input_tokens=10, output_tokens=2),
                ModelResponse(text="APPROVE", input_tokens=10, output_tokens=2),
            ]
        ),
        env=MockEnvironment(
            exec_results={
                "pytest tests/ -x --tb=short": 0,
                "gh pr create *": "https://example.test/pr/4",
            }
        ),
    )

    result.assert_passed()
    assert result.state.security_verdict == "approved"
    assert result.state.correctness_verdict == "approved"
    assert result.state.council_passed is True
    result.assert_node_skipped("fix_council_feedback")
    result.assert_node_skipped("fix_tests")
