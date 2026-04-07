# Real Examples

This directory is for true dogfood workflows where CodeMinions works on its own repo.

These examples are different from both:
- `examples/research/`: research-faithful pattern pressure tests
- `examples/validation/`: small real-world validation runs

Real examples should:
- use a real model
- run against this repo
- use isolated git worktrees
- have binary acceptance checks
- print evidence, not storytelling

Real work is not limited to single files.
Tasks may target:
- a file
- a group of related files
- a folder or subsystem

The point is narrow, reviewable, acceptance-driven repository work.

Current files:
- `01_self_hosted_single_task.py`
- `02_self_hosted_task_queue.py`
