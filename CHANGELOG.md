# Changelog

All notable changes to CodeMinions are documented here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

## [0.1.0] — 2026-04-07

### Added

**Core primitives**
- `Blueprint` — ordered node list with validation, composition (`.before`, `.after`, `.replace`, `.without`, `+`)
- `AgentNode` — LLM loop with tool calling, `max_rounds`, `on_max_rounds`, `token_budget`, `max_iterations`
- `DeterministicNode` — pure Python, guaranteed outcome, sync and async
- `JudgeNode` — LLM evaluates prior agent output; APPROVE/VETO with retry; `max_vetoes`, `on_veto`
- `ParallelNode` — concurrent child execution with merged state
- `LoopNode` — iterates a sub-blueprint over discovered targets; per-iteration round budget reset
- `Task` — structured input: `description`, `context`, `acceptance`, `constraints`, `metadata`
- `RunContext` — shared spine across nodes: env, state, trace, model, config, task
- `RunResult` / `EscalationResult` — structured run output with diff, branch, trace, tokens

**Environments**
- `DockerEnv` — full runtime isolation; env-file injection, port reservation, safe `put_archive` writes
- `GitWorktreeEnv` — code isolation via git worktrees; pool support for parallel runs
- `LocalEnv` — no isolation; local dev and testing

**Models**
- `ClaudeModel` — Anthropic Claude adapter (`ANTHROPIC_API_KEY` or `ANTHROPIC_API_TOKEN`)
- `OpenAIModel` — OpenAI adapter

**Built-in tools**
- `CODE_TOOLS` — read_file, write_file, edit_file, grep, glob, list_dir
- `SHELL_TOOLS` — run_command, git_diff, git_log, git_status, git_add, git_commit, diff_history
- `CI_TOOLS` — run_tests, run_linter, get_test_output
- `WEB_TOOLS` — web_fetch, web_search
- `PROGRESS_TOOLS` — write_todos, get_todos

**MCP**
- Full MCP client subsystem: `mcp_tools`, `register_mcp_server`, `MCPServerConfig`
- Transports: stdio, streamable_http, sse
- Resources, prompts, completions, subscriptions, direct `MCPClient` access
- Environment variable configuration (`MINION_MCP_<NAME>_COMMAND` etc.)

**Testing**
- `MockModel` — replays scripted `ModelResponse` objects; raises `MockExhaustedError` if exhausted
- `MockEnvironment` — in-memory filesystem + exec matching (exact, then glob)
- `run_blueprint_test` — no-API-call blueprint execution for contract tests

**Configuration resolution**
- `Minion` resolves: constructor args > `minion.toml` > `pyproject.toml [tool.minion]` > env vars > defaults
- String shorthands: `model="claude-sonnet-4-6"`, `environment="docker"`, `blueprint="coding"`
- Auto-detects model from `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`
- Auto-finds project root by walking up for `.git` or `pyproject.toml`

**Trace introspection**
- `Trace.by_type(event_type)` — filter events by type
- `Trace.by_node(node)` — filter events by node name
- `Trace.tool_calls(name=None)` — get tool call events, optionally by tool name
- `RunResult.assert_judge_approved(node)` — assert judge APPROVE verdict
- `RunResult.assert_judge_vetoed(node, reason=None)` — assert judge VETO
- `RunResult.judge_verdicts()` — `{node: "approved" | "vetoed: <reason>"}` map

**Built-in blueprints**
- `coding_blueprint` — Stripe-pattern: gather → implement → lint → test → commit → push

**Examples (contract tests)**
- `01_stripe_pattern` — sequential hybrid workflow
- `02_spotify_judge` — JudgeNode with veto + retry
- `03_airbnb_migration` — LoopNode per-file iteration
- `04_linkedin_spec` — structured Task with acceptance criteria
- `05_anthropic_two_agent` — two-agent handoff via state
- `06_ramp_docker` — DockerEnv with real services
- `07_coinbase_council` — ParallelNode multi-domain judges
- `08_real_llm_smoke` — real model smoke test
- `09_real_repo_config_resolution` — SDK self-improvement against its own repo

---

[Unreleased]: https://github.com/tamilarasan/workflows/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/tamilarasan/workflows/releases/tag/v0.1.0
