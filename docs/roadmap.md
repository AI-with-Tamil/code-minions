# Roadmap & Reliability Plan

This document ties the research-backed design to the work we need to finish before the SDK can be considered production ready.

## Research anchors

- **Task → Blueprint → Branch**: the ordered workflow model from AGENTS.md and the 17-company study guides every decision.  
- **Environment discipline**: DockerEnv must remain the production path, with GitWorktreeEnv/LocalEnv reserved for tests/local runs.  
- **Tool surface focus**: file + search + shell + CI tools, plus MCP connectors, should be explicitly wired into the RUNNER before adding new abstractions.  
- **Reliability boundaries**: `done()`, judges, bounded retries, deterministic validation loops, and deterministic tool outputs form the shield around the probabilistic agent behavior.

## Current milestones

1. **Examples as contracts**: keep examples/01–09 executable via tests (`tests/test_examples_contracts.py`) and align docs with their stories.  
2. **Tool surface hardening**: file/edit, search, shell, CI, web, MCP, and progress tools now exist; refine quoting/errors, add docs, and keep Shell as an actuator.  
3. **DockerPath completion**: DockerEnv must respect env files, port ranges, safe exec semantics, and be covered by tests + docs.  
4. **Mocked baseline**: add regression tests that mirror the real workflow (e.g., example 09) using MockModel/MockEnvironment plus deterministic `done()` coverage.  
5. **Real run recipe**: complete `.env` guidance and `uv run python examples/09_real_repo_config_resolution.py` script to prove the SDK against live LLMs.

## Next reliability checkpoints

| Deliverable | Why it matters |
|-------------|---------------|
| `.env` template + run script for example 09 | Shows the SDK handling a full repo edit with real credentials |
| Regression test for example 09 workflow | Guarantees the logic remains sound without calling LLMs |
| DockerEnv doc + tests | Documents container boundaries in line with research; keeps sandbox safe |
| `docs/api/` refinement for tool surfaces | Keeps public contract aligned with research-backed tool assumptions |
| Trace/RunResult introspection helpers | Makes verifying `done()` and `JudgeNode` outputs deterministic |

## How to work from here

1. **Document** each real-worl workflow you want to ship (start with example 09).  
2. **Test** the workflow with MockModel/MockEnvironment, covering the nodes, tools, and judge path.  
3. **Run** the workflow with real keys (per the `.env` recipe) and capture branch/diff + trace evidence.  
4. **Harden** the tool chain (Docker, shell, search, CI) with safe quoting, structured errors, and dedicated docs referencing the research.  
5. **Expand** the roadmap doc list (`docs/next-work.md`, `docs/research-notes.md`) whenever a new research insight needs tracking.  

Treat each doc as actionable guidance rather than a brainstorm. If it can’t be automated/tested, document why and how the manual step fits into the contract.
