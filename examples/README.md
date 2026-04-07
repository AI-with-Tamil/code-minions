# Examples Directory

This directory contains three kinds of examples.

They are both valuable, but they serve different jobs.

## 1. Research Examples

Purpose:
- mirror what we understand from company blogs, papers, and public writeups
- pressure-test whether CodeMinions can express those workflows honestly
- expose where the SDK is natural versus awkward

Current files:
- `research/01_stripe_pattern.py`
- `research/02_spotify_judge.py`
- `research/03_repository_migration.py`
- `research/04_linkedin_spec.py`
- `research/05_anthropic_two_agent.py`
- `research/06_ramp_docker.py`
- `research/07_coinbase_council.py`

These should be read as:
- research-faithful where possible
- approximations where necessary
- pressure tests for SDK design, not literal reproductions of internal company systems

## 2. Validation Examples

Purpose:
- prove the SDK works with real models, real repos, and real environments
- validate the runner and acceptance loop under actual execution

Current files:
- `validation/08_real_llm_smoke.py`
- `validation/09_real_repo_config_resolution.py`

These are not company-story examples.
They exist to catch reality.

## 3. Real Examples

Purpose:
- use CodeMinions to do real work on the `code-minions` repo itself
- run in isolated git worktrees
- support narrow, acceptance-driven tasks whose context may be files or folders

Current files:
- `real/01_self_hosted_single_task.py`
- `real/02_self_hosted_task_queue.py`

These are dogfood workflows.
They should print evidence, not tell a research story.

## Maintenance Rule

When editing an example, always state implicitly or explicitly:
- is this a research example or a validation example?
- what is directly modeled by CodeMinions?
- what is approximated with deterministic setup or mocked infrastructure?
- what limitation in the SDK does this example expose?

## Current Cleanup Direction

- keep validation examples small and runnable
- make research examples more faithful to source material
- remove unsupported mythology and weakly sourced claims
- preserve awkwardness where it reveals SDK design pressure
