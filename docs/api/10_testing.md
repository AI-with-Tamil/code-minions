# Testing

Test blueprints without real API calls. No network. No environment setup.

## Core function

```python
from codeminions.testing import run_blueprint_test

result: RunResult = await run_blueprint_test(
    blueprint: Blueprint,
    task:      str | Task,
    model:     MockModel,
    env:       MockEnvironment,
)
```

---

## MockModel

Replays a scripted sequence of responses. No API calls.

```python
from codeminions.testing import MockModel, ModelResponse, ToolCall

mock = MockModel(
    responses=[
        ModelResponse(tool_calls=[
            ToolCall("read_file", {"path": "src/auth.py"}),
        ]),
        ModelResponse(tool_calls=[
            ToolCall("edit_file", {
                "path": "src/auth.py",
                "old":  "return user.token",
                "new":  "if user is None:\n    return None\nreturn user.token",
            }),
        ]),
        ModelResponse(tool_calls=[
            ToolCall("done", {
                "summary":       "Added null guard in authenticate",
                "files_changed": ["src/auth.py"],
            }),
        ]),
    ]
)
```

### Behavior

- Responses consumed in order per AgentNode execution
- If responses exhausted before `done()` called → `MockModel` raises `MockExhaustedError`
- Multiple AgentNodes in one blueprint → `MockModel` tracks position per node

---

## MockEnvironment

In-memory filesystem and command execution. No real files or processes.

```python
from codeminions.testing import MockEnvironment

env = MockEnvironment(
    files: dict[str, str] = {},          # path → content
    exec_results: dict[str, int | str] = {},  # cmd → exit_code or stdout
)
```

### exec_results

```python
env = MockEnvironment(
    files={
        "src/auth.py": "def authenticate(user):\n    return user.token\n",
    },
    exec_results={
        "ruff check . --fix":       0,          # exit code 0 = success
        "pytest tests/ -x --tb=short": 0,
        "git checkout -b codeminions/abc123": 0,
        "git add -A":               0,
        "git commit -m ...":        0,           # glob match: "git commit -m *"
    },
)
```

### Behavior

- `read()` → returns from `files` dict; raises `FileNotFoundError` if missing
- `write()` → updates `files` dict in memory
- `edit()` → applies old→new replacement in `files` dict
- `exec()` → matches cmd against `exec_results` keys (exact match, then glob match)
- `exec()` cmd not in `exec_results` → raises `MockCommandNotFoundError`
- All operations recorded — queryable via `env.calls`

---

## Full example

```python
from codeminions.blueprints import coding_blueprint
from codeminions.testing import MockModel, MockEnvironment, ModelResponse, ToolCall, run_blueprint_test

async def test_coding_blueprint_happy_path():
    result = await run_blueprint_test(
        blueprint=coding_blueprint,
        task="Fix null check in auth",
        model=MockModel(responses=[
            ModelResponse(tool_calls=[ToolCall("read_file", {"path": "src/auth.py"})]),
            ModelResponse(tool_calls=[ToolCall("edit_file", {"path": "src/auth.py", "old": "...", "new": "..."})]),
            ModelResponse(tool_calls=[ToolCall("done", {"summary": "Fixed", "files_changed": ["src/auth.py"]})]),
        ]),
        env=MockEnvironment(
            files={"src/auth.py": "def authenticate(user):\n    return user.token\n"},
            exec_results={
                "ruff check . --fix":          0,
                "pytest tests/ -x --tb=short": 0,
                "git checkout -b *":           0,
                "git add -A":                  0,
                "git commit -m *":             0,
                "git push *":                  0,
                "gh pr create *":              "https://github.com/org/repo/pull/42",
            },
        ),
    )

    result.assert_passed()
    result.assert_node_ran("implement")
    result.assert_node_skipped("fix_lint")
    result.assert_node_skipped("fix_tests")
    result.assert_tool_called("edit_file", path="src/auth.py")
    result.assert_tokens_under(10_000)
```

---

## pytest integration

```python
# conftest.py
import pytest

@pytest.fixture
def clean_env():
    return MockEnvironment(
        files={"src/auth.py": "..."},
        exec_results={"ruff check . --fix": 0, "pytest tests/ -x": 0, ...},
    )
```
