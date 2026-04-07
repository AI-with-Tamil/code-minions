# Next Work

This file is the practical follow-on to `docs/roadmap.md`.
It answers: what should the next agent actually do from here?

## First Principle

Do not start by adding features.
Start by asking which of these you are working on:
- primitive discipline
- real-run reliability
- contract hardening
- evidence-driven expansion

If the work does not fit one of those, it is probably not the next best use of time.

## Immediate Priorities

### 1. Keep Validation Workflows Alive

Why:
- they are the fastest way to catch where the SDK breaks in reality

Next actions:
- keep the self-repo worktree run healthy
- add or maintain at least one Docker-isolated validation workflow
- add or maintain at least one MCP-assisted validation workflow
- document blockers when a real run fails because of environment, not SDK logic

### 2. Separate Research Examples From Validation Examples

Why:
- these examples serve different jobs and should not distort each other

Next actions:
- relabel or reorganize examples by purpose
- preserve small real validation workflows
- make research examples explicitly mark what is direct, approximated, or not first-class

### 3. Tighten Primitive Boundaries

Why:
- the main post-v1 risk is accidental API inflation

Next actions:
- review proposed additions against the primitive-promotion rules in `AGENTS.md`
- keep company-specific infrastructure out of the core unless repeated evidence proves otherwise
- capture repeated awkwardness before promoting new abstractions

### 4. Expand Contract Tests Around Invariants

Why:
- after v1, invariants matter more than raw feature count

Next actions:
- add tests for config precedence edge cases
- add tests for escalation and diagnostic detail
- add tests for trace/query helper stability
- add tests for environment guarantees and isolation assumptions

## Medium-Term Priorities

- multi-repo dependency support in `GitWorktreeEnv`
- cost governance across `run_batch`
- flaky test classification in `CI_TOOLS`
- structured feedback loops from PR comments back into `Task.context`
- helper utilities for per-node MCP tool curation

These are candidates, not automatic promotions into the primitive layer.

## How To Choose The Next Task

Prefer tasks that do one of these:
- remove ambiguity from the core API
- make a real validation workflow pass
- convert repeated example awkwardness into a justified helper or built-in
- improve diagnostics when the agent fails

Avoid tasks that mainly do one of these:
- imitate company infrastructure for its own sake
- widen the core surface without repeated evidence
- replace real validation with cleaner storytelling

## Expected Working Style

When you make an SDK change:
1. update the relevant contract docs
2. add or update mock tests
3. run the narrowest useful test slice
4. if the change matters in practice, run a real validation workflow
5. record any repeated awkwardness as future roadmap evidence

## Success Signal

The project is moving correctly when:
- a new agent can read `AGENTS.md` and immediately understand what belongs in the SDK
- examples are more honest about approximation
- real runs catch real issues early
- the SDK surface grows slowly and intentionally
