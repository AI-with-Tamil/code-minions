# GitHub Maintenance

This repo is an SDK, not an app.
Maintain Git and GitHub like public API infrastructure, not like a scratch project.

## Repository Baseline

Current expectations:

- default branch should be `main`
- every meaningful change should land through a focused branch
- examples, docs, implementation, and tests must stay aligned
- public API changes must be visible in both docs and examples

## First-Time Setup

If the repo has no clean Git history yet:

```bash
git branch -M main
git add .
git commit -m "chore: initialize code-minions baseline"
git remote add origin <github-repo-url>
git push -u origin main
```

## Branch Strategy

Use short-lived branches.
One branch should represent one coherent change.

Good branch names:

- `docs/api-contract-alignment`
- `core/agent-retry-semantics`
- `testing/example-coverage`
- `env/docker-runtime-fixes`
- `release/v0.1.0-prep`

Avoid:

- `work`
- `update`
- `changes`
- long-running mixed-purpose branches

## Commit Strategy

Each commit should explain one user-visible or contract-visible change.

Preferred commit prefixes:

- `docs:`
- `feat:`
- `fix:`
- `refactor:`
- `test:`
- `build:`
- `chore:`

Examples:

- `docs: align v1 contract around LoopNode and DockerEnv`
- `fix: enforce AgentNode max_rounds during judge retries`
- `test: cover run_stream and diff capture behavior`
- `build: export public API from codeminions package`

Avoid vague commit messages like:

- `update`
- `changes`
- `more work`
- `fix stuff`

## What Must Change Together

For this repo, these should usually move together:

- public API docs
- examples
- implementation
- tests

Rules:

- if public API changes, update `docs/api/`
- if usage changes, update the affected example(s)
- if runtime behavior changes, add or update tests
- if design direction changes, update `AGENTS.md`

Do not let docs or examples drift behind implementation.

## Pull Request Discipline

Even if working alone, use PRs as design checkpoints.

Every PR should answer:

1. What changed in the public contract?
2. What changed in behavior?
3. Which examples are affected?
4. Which docs are affected?
5. What tests prove the change?
6. Is this breaking?

PR titles should be specific:

- `Fix AgentNode retry semantics`
- `Align docs and examples around LoopNode`
- `Add testing coverage for judge and streaming behavior`

## Labels

Use labels by area so the repo stays navigable:

- `api`
- `docs`
- `examples`
- `core`
- `env`
- `models`
- `tools`
- `testing`
- `release`
- `breaking-change`

## Release Discipline

SDK users need version anchors.
Tag every meaningful release.

Basic release flow:

```bash
uv run pytest -q
git switch main
git pull --ff-only
git tag v0.1.0
git push origin main --tags
```

Before tagging:

- tests pass
- docs match implementation
- examples still express the intended API cleanly
- exported symbols in `src/codeminions/__init__.py` are intentional

## Main Branch Rules

`main` should stay:

- releasable
- tested
- coherent with docs

Do not push experimental mixed work directly to `main`.

## SDK-Specific Review Standard

When reviewing a change, ask:

- does this alter the public API?
- is the abstraction real or just implementation convenience?
- does it make examples cleaner or more awkward?
- does it improve or weaken long-term API stability?
- does it add primitive sprawl?
- are failure modes still explicit and testable?

## Recommended Working Loop

For normal work:

```bash
git switch -c <topic-branch>
# make focused changes
uv run pytest -q
git add <files>
git commit -m "<type>: <specific change>"
git push -u origin <topic-branch>
```

Then open a PR and review the change from the SDK user's point of view.

## Source Of Truth

For this repo, contract order is:

1. `AGENTS.md`
2. `docs/api/`
3. `examples/`
4. implementation in `src/codeminions/`

If implementation disagrees with the contract, fix the implementation or explicitly update the contract.
