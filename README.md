# CodeMinions

Python SDK for building unattended coding harnesses that turn a task into a reviewable branch or PR.

This repo is building primitives, not a chat app and not a general workflow engine.
The core model is:

```text
Task -> Blueprint -> Branch
```

## Current contract

The live source of truth is:

- [AGENTS.md](/Users/tamil/Developers/workflows/AGENTS.md)
- [`examples/`](/Users/tamil/Developers/workflows/examples)
- [`docs/api/`](/Users/tamil/Developers/workflows/docs/api)
- [GitHub maintenance guide](/Users/tamil/Developers/workflows/docs/github-maintenance.md)
- [Real LLM run guide](/Users/tamil/Developers/workflows/docs/real-llm-run.md)
- [Roadmap & reliability plan](docs/roadmap.md)

If one of those disagrees with older design notes, the current contract wins.

## How To Read This Repo

This repo has two different kinds of workflows:

- Research examples: research-faithful reference workflows that pressure-test whether CodeMinions can express patterns seen in company blogs and papers.
- Validation examples: small real-world runs that prove the SDK works with real models, real repos, and real environments.

These are not the same thing as the primitive SDK surface.
Research is input.
Examples are pressure tests.
The SDK API is the output.

## Core primitives

- `Task`: structured input contract
- `Tool`: typed executable capability
- `Node`: deterministic, agentic, judge, parallel, and loop workflow steps
- `Blueprint`: ordered workflow definition
- `Environment`: `DockerEnv` for production, `GitWorktreeEnv` and `LocalEnv` for local use
- `Minion`: runner that executes a task against a blueprint

## Design stance

- deterministic + agent hybrid, not pure free-form agenting
- `DockerEnv` is the production path
- human review happens at the end
- bounded retries and explicit escalation
- examples are pressure tests for API design, not the API itself

## Post-v1 build rule

The SDK now has a v1.
From here, the main job is not adding more surface area by default.
The main job is:

- preserving a small primitive layer
- tightening contracts and failure semantics
- validating with real runs
- only promoting abstractions that recur across multiple workflows

## Status

- implementation in `src/codeminions/` exists and is being hardened after the first v1 pass
- `AGENTS.md` defines what counts as a primitive, helper, built-in pattern, or example-only behavior
- public examples are backed by executable contract tests in `tests/test_examples_contracts.py`
- MCP support now lives under `src/codeminions/tools/mcp/` as a package-level client subsystem
- research and design references live under `design/`

## Real validation

Run `examples/validation/09_real_repo_config_resolution.py` with your real model keys to validate CodeMinions:

1. Populate `/Users/tamil/Developers/workflows/.env` with the Anthropic/OpenAI credentials, base URL overrides, and model aliases you need.
2. Start Docker locally so `DockerEnv` can launch containers (`python:3.12` is the default image).
3. Execute `uv run python examples/validation/09_real_repo_config_resolution.py` from the repo root.
4. Inspect the generated branch/diff and trace output to confirm `done()` was hit and acceptance criteria satisfied.

The [roadmap](docs/roadmap.md) lays out how that workflow maps to our reliability goals.
