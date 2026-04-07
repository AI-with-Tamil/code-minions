# TODO

Minion SDK implementation backlog for the coding agent.

Read first before changing code:
1. `CLAUDE.md`
2. `AGENTS.md`
3. `README.md`
4. `docs/api/`
5. `examples/`
6. `tests/`

Contract rule:
- `AGENTS.md`, `docs/api/`, `examples/`, and `tests/` are the live contract.
- If older design notes disagree, the current contract wins.

Current validated baseline:
- `58 passed`
- example contract tests exist in `tests/test_examples_contracts.py`
- config resolution contract implemented
- judge retry contract tightened
- MCP client package exists

Do not:
- revert unrelated local changes
- weaken examples to fit implementation
- add speculative abstractions
- hide weak runtime behavior behind prompt text

Do:
- build the smallest strong fix
- add tests with every meaningful contract change
- keep docs aligned when the contract becomes sharper

---

## Priority 1 — Finish The Built-In Coding Tool Surface

Goal:
Make the built-in tools strong enough for unattended coding workflows across the public examples.

Primary files:
- `src/minion/tools/code.py`
- `src/minion/tools/search.py`
- `src/minion/tools/shell.py`
- `src/minion/tools/ci.py`
- `src/minion/tools/__init__.py`
- `tests/test_tools.py`

Implement or harden:

### Code / File tools
- `read_file`
- `write_file`
- `edit_file`
- `append_file`
- `insert_before`
- `insert_after`
- `replace_regex`
- `file_exists`
- `list_dir`

### Search / Context tools
- `grep`
- `glob`
- `find_files` or `search_files`
- add small deterministic helpers only if they clearly improve the examples

### Shell / Git tools
- `run_command`
- `pwd`
- `git_status`
- `git_diff`
- `git_log`
- `git_show`
- `git_add`
- `git_commit`
- `git_checkout`
- `git_create_branch`
- `git_push`
- `diff_history`

### CI / Feedback tools
- `run_tests`
- `run_linter`
- `get_test_output`
- `get_lint_output`
- `summarize_failure_output`

Requirements:
- outputs bounded and useful to the model
- git helpers non-interactive
- shell failures returned clearly, not as crashes
- file edit tools fail clearly on bad preconditions
- examples should feel naturally supported by the tool layer

Tests to add/update:
- file edit edge cases
- search helper behavior
- shell output formatting
- git helper command construction
- CI summarization behavior
- example compatibility where useful

Definition of done:
- tool surface matches the examples and docs materially better
- tests cover the added contract
- `uv run ruff check .`
- `uv run pytest -q`

---

## Priority 2 — Harden `done()` / Agent Completion Semantics

Goal:
Keep `done()` as the canonical completion signal, but make the runtime less brittle when real work is already complete.

Problem:
- real self-hosted run in `examples/09_real_repo_config_resolution.py` escalated because the agent exhausted budget without calling `done()`
- the primitive is correct; the runtime around it is still too brittle

Primary files:
- `src/minion/_internal/loop.py`
- `src/minion/_internal/engine.py`
- `src/minion/core/node.py`
- `src/minion/core/minion.py`
- tests

Expected direction:
- keep `done()` as a runtime-owned control tool
- improve prompt/tool ergonomics so agents call it sooner
- consider deterministic success handling only where a workflow already proves success via a follow-up verifier
- do not turn completion into vague text heuristics

Add tests for:
- agent finishes correctly with `done()`
- exhausted loop still escalates when appropriate
- verifier-driven workflows do not fail only because final ceremony was missed, if that contract is explicitly supported

Definition of done:
- completion behavior is more reliable in real runs
- semantics are explicit in code and tests

---

## Priority 3 — Tighten ParallelNode State Semantics

Goal:
Make `ParallelNode` behavior deterministic enough for council-style workflows.

Problem:
- current implementation shares one mutable `ctx.state` across concurrent children
- council-style workflows can become timing-dependent

Primary files:
- `src/minion/_internal/engine.py`
- `src/minion/core/node.py`
- `docs/api/04_nodes.md`
- tests

Expected direction:
- decide whether parallel children:
  - mutate shared state directly, or
  - work on isolated child views and merge deterministically
- encode that choice explicitly
- make tests prove the behavior

Definition of done:
- `ParallelNode` semantics are no longer timing-dependent by accident
- council example remains natural

---

## Priority 4 — Improve Example 09 As The First Internal Product Run

Goal:
Make `examples/09_real_repo_config_resolution.py` a reliable self-hosted Minion run on this repo.

Primary files:
- `examples/09_real_repo_config_resolution.py`
- runtime files only if required

What to improve:
- reduce unnecessary token burn
- make the run finish cleanly more often
- preserve the narrow task scope
- keep it safe for this repo

Success criteria:
- uses the real configured model path
- runs in `GitWorktreeEnv`
- completes the documented config-resolution task cleanly
- serves as a serious “use our product on ourselves” example

---

## Priority 5 — Documentation Sweep After Runtime/Tools Settle

Goal:
Only after the runtime/tool surface is stronger, do a doc sweep for remaining drift.

Files likely involved:
- `README.md`
- `AGENTS.md`
- `docs/api/02_tool.md`
- `docs/api/04_nodes.md`
- `docs/api/05_blueprint.md`
- `docs/api/08_minion.md`
- `docs/api/09_result.md`

Focus:
- tool surface
- completion semantics
- parallel semantics
- example support boundaries

---

## Working Notes For The Coding Agent

Use the examples plus research to predict missing practical surface.
Do not use research as an excuse to add framework sprawl.

Good changes:
- make examples more natural
- improve determinism
- improve traceability
- improve testability
- reduce ambiguity

Bad changes:
- expose internals
- invent new primitives casually
- replace code guarantees with prompt suggestions
- widen public surface without repeated pressure from examples or research

When you finish a meaningful slice:
1. run `uv run ruff check .`
2. run `uv run pytest -q`
3. summarize:
   - what contract gap was fixed
   - what files changed
   - what remains weak
