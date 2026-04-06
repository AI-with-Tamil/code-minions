# Minion SDK

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

If one of those disagrees with older design notes, the current contract wins.

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
- examples are contract tests for API design

## Status

- examples define the intended API
- implementation in `src/minion/` exists and is being refined toward that contract
- MCP support now lives under `src/minion/tools/mcp/` as a package-level client subsystem
- research and design references live under `design/`
