#+ Next Work & Research Integration

This file captures the ultra-deep research directions and actionable doc/tasks for building the *full* Minion SDK. Each entry is drawn directly from the research/AGENTS thesis and represents future work that should unblock the real-LAM/production experience.

## Phase 1: Reliability groundwork (derived from `design/research/`)

1. **Real workflow validation** (`examples/09_real_repo_config_resolution.py`):
   - Document `.env` and Docker readiness.
   - Scripted run instructions + verification checklist (branch, diff, summary, trace).  
2. **Mocked contract tests**:
   - Mirror the real workflow using `MockModel`/`MockEnvironment`.
   - Assert `done()` invocation, tool bookkeeping, and judge responses.  
3. **Tool surface completion**:
   - Strengthen Shell/CODE/SEARCH/CI tools to be explicit, quoted, bounded, and IDE-friendly (Claude Code style).
   - Document each tool’s contract in `docs/api/02_tool.md` and `docs/api/04_nodes.md`.
4. **DockerEnv isolations**:
   - Enforce env files, port allocation, safe `exec` args, and capability limits.
   - Test the lifecycle (setup, exec, cleanup) with integration mocks.

## Phase 2: Production features

1. **Trace + RunResult introspection**:
   - Document how to read `RunResult.trace`.
   - Add helpers to assert tool calls and judge verdicts (for real runs).
2. **MCP ecosystem**:
   - Expand `docs/api/02_tool.md` with MCP server examples.
   - Align `AGENTS.md` instructions with the MCP package.
3. **Release hygiene**:
   - Lock down version policy, changelog, release tags.
   - Build GitHub templates referenced in `docs/github-maintenance.md`.

## Phase 3: Visionary research tie-ins

1. **Claude Code / Deep Agents triage**:
   - Capture insights from `design/research/` into `docs/research-notes.md`.
   - Ensure future skill/docs updates track the `CLAUDE.md` prompt evolution.
2. **UX for feedback loops**:
   - Document how to read judge feedback, progress files, and `done()` summaries.
   - Bridge doc coverage between `docs/api/08_minion.md` and real run outputs.
3. **Automated reliability audits**:
   - Introduce scripts or tests that re-run example 09 under `MockModel`+`DockerEnv` variations.
   - Report on tokens, iterations, and judge outcomes as part of CI.

Each of these sections should eventually become tracked issues/PRs. Keep this document updated with new research findings and the next deliverable you or another agent should tackle.
