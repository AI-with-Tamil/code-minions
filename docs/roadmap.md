# Roadmap & SDK Building Process

This document explains how to build CodeMinions after the first v1 exists.

The project is no longer in the "invent primitives freely" stage.
It is now in the "protect the primitive layer, validate in reality, and only promote repeated patterns" stage.

## The Post-v1 Goal

The goal from here is not feature count.
The goal is a primitive SDK that becomes harder to misuse over time.

That means:
- keep the core surface small
- preserve clear mental models
- harden contracts and failure semantics
- use real runs to catch reality
- let repeated workflow pressure, not enthusiasm, determine what becomes first-class

## The Four Parallel Tracks

All meaningful SDK work should fit into one of these tracks.

### 1. Primitive Discipline

Question:
What belongs in the SDK core, and what does not?

Focus:
- classify new ideas as primitive, built-in pattern, helper, example-only, or out of scope
- avoid accidental API inflation
- keep `Task -> Blueprint -> Branch` intact

Success criteria:
- new abstractions are rare and justified
- naming and defaults stay coherent
- examples do not silently redefine the core

### 2. Real-Run Reliability

Question:
Does the SDK survive actual execution, not just mocks?

Focus:
- real model calls
- real repo mutation in isolated worktrees
- Docker-isolated execution
- MCP-assisted runs
- failure and escalation behavior

Success criteria:
- validation workflows remain runnable
- mock tests and real runs tell the same story
- failure modes are inspectable and actionable

### 3. Contract Hardening

Question:
What must never become ambiguous?

Focus:
- explicit `done()` completion
- bounded retries
- escalation semantics
- config precedence
- trace and result invariants
- environment isolation behavior

Success criteria:
- contract tests catch regressions early
- real diagnostics remain stable enough for users and tooling
- defaults stay unsurprising

### 4. Evidence-Driven Expansion

Question:
What repeated pain deserves promotion into the SDK?

Focus:
- repeated awkwardness across research examples
- repeated friction in real validation runs
- repeated helper patterns that want to become built-ins

Success criteria:
- promotion decisions are evidence-based
- one-off company patterns stay out of the core
- roadmap items come from pressure, not brainstorming

## Primitive Promotion Rules

Before adding a primitive, answer:

1. What workflows cannot be expressed cleanly without it?
2. Does it recur across multiple independent workflows?
3. Is it truly primitive, or a helper around existing primitives?
4. Can it be tested without real APIs?
5. Will a user reasonably expect it in the core SDK?
6. Does it preserve the current mental model?

Decision guideline:
- one example needs it: keep it in the example/helper layer
- repeated example awkwardness: investigate
- repeated example awkwardness plus real-run pain: consider promotion

## Example Strategy

Examples should be split conceptually into two groups.

### Research Examples

Purpose:
- model workflows from blogs, papers, and company writeups as faithfully as possible
- expose where CodeMinions is natural versus awkward

Rules:
- clearly mark what is direct, approximated, or not first-class
- do not present approximations as native SDK guarantees
- use awkwardness as roadmap evidence

### Validation Examples

Purpose:
- prove the SDK works with real models, repos, environments, and acceptance loops

Rules:
- keep them small and repeatable
- they are not company-story examples
- do not drop them just because they are not research-faithful

## Real Validation Matrix

The preferred validation set is:
- tiny local smoke run
- self-repo worktree run
- Docker isolated run
- MCP-assisted run

This matrix should stay alive as the SDK evolves.
When mocks and real runs disagree, the real run should drive the next fix.

## Current Priorities

1. Freeze and document primitive boundaries in `AGENTS.md`
2. Keep validation workflows healthy, especially worktree-backed self-hosted runs
3. Rewrite research examples to be more faithful without silently changing the SDK contract
4. Use example awkwardness to identify helpers or future built-ins
5. Continue tightening trace, result, and failure semantics

## What Not To Do

- Do not add primitives because they sound useful
- Do not let a single company pattern dictate the SDK architecture
- Do not confuse company infrastructure with CodeMinions surface area
- Do not delete real validation workflows in favor of cleaner storytelling
- Do not widen the API before repeated evidence demands it

## Definition Of Progress

Progress after v1 means:
- the primitive layer gets clearer
- tests get stricter
- real runs get more repeatable
- examples get more honest
- new agents entering the repo can tell what belongs in the SDK and what does not
