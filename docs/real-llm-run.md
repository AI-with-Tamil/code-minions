# Real LLM Run

Use this when you want a real end-to-end CodeMinions run with an actual model.

## Safe first run

This repo includes a smoke example that runs against a temporary git repo and does not push or open PRs:

```bash
ANTHROPIC_API_KEY=... uv run python examples/validation/08_real_llm_smoke.py
OPENAI_API_KEY=... uv run python examples/validation/08_real_llm_smoke.py --model gpt-4o
```

What it exercises:
- real model adapter
- real tool loop
- real file edits
- real local command execution
- real git branch creation
- real test execution

What it does not do:
- push to a remote
- create a PR
- mutate this working repo

## Before running

- set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
- make sure network access is allowed for the run
- expect model cost; this is not a mock test

## After the smoke run

Then move to repo-bound examples like `examples/04_linkedin_spec.py`, but only after:
- replacing the task with one that matches the target repo
- removing or adapting any `gh pr create` / `git push` steps
- making sure acceptance commands are real for that codebase

## Full repo run (Example 09)

Example 09 runs CodeMinions against this repo itself in an isolated git worktree.

```bash
# 1. Credentials (at least one key required)
cp .env.example .env   # fill in ANTHROPIC_API_KEY or ANTHROPIC_API_TOKEN

# 2. Run
uv run python examples/validation/09_real_repo_config_resolution.py
```

**Verification checklist:**

| Field | Expected |
|-------|----------|
| `outcome` | `passed` |
| `branch` | `codeminions-real-<hash>` |
| `diff` | non-empty (changes to `src/codeminions/`) |
| `acceptance` | `True` |
| `escalated` | absent |

The worktree is kept on disk after the run (`cleanup_on_complete=False`). Inspect it at the printed `worktree` path. To clean up manually:

```bash
git worktree list                          # find the path
git worktree remove <path> --force
```
