# Research Notes — CodeMinions Design Guidance

Synthesized from `design/research/` (7-direction validation, 8-company case studies, Anthropic agent patterns).
Use this when making design decisions — each section ends with an actionable SDK constraint.

---

## 1. The Blueprint Hybrid Is The Gap

Every production team (Stripe, Spotify, Ramp, Coinbase, LinkedIn) independently built the same pattern:
an ordered sequence of deterministic steps interleaved with agentic loops — not a graph, not a chat.
No Python SDK exposed this as an ergonomic primitive. The academic term is "Blueprint First, Model Second"
(arxiv:2508.02721).

**SDK constraint:** `Blueprint` is an ordered list, not a graph. `DeterministicNode` and `AgentNode`
are first-class coequals. The hybrid is the product, not a convenience layer over a graph executor.

---

## 2. Environments: Code Isolation ≠ Runtime Isolation

Git worktrees went mainstream in 2025 (Boris Cherny called them "the #1 productivity tip"; Claude Code
has built-in worktree subagents). But worktrees only isolate code — they share ports, DBs, build caches,
and `.env` files. Two agents on separate worktrees both trying to bind `localhost:3000` will conflict.

Stripe runs pre-warmed AWS EC2 devboxes (10-second spin-up) with full isolation. Dagger Container Use
is the closest OSS equivalent.

**SDK constraint:**
- `GitWorktreeEnv` is local dev / testing only — document this hard
- `DockerEnv` is the production path — one container per run, `network="none"` default
- `WorktreePool` is valuable for test parallelism; not a substitute for container isolation at scale
- Never position `GitWorktreeEnv` as production-safe for concurrent agents

---

## 3. Shift-Left Feedback: The 2-Round Cap

Stripe's most-cited design decision: hard cap of 2 CI rounds, then escalate. Not 3, not "retry until
fixed". The validated pattern from the 17-company study:

```
Tier 0: Static/AST    < 100ms    import errors, parse failures
Tier 1: Lint          < 5s       ruff/eslint, autofix where possible
Tier 2: Tests         < 60s      related tests only (changed file → test mapping)
Tier 3: CI            minutes    max 2 rounds, then escalate
```

Spotify's "Honk" system adds a JudgeNode (LLM judge) that rejects ~25% of attempts for scope creep.
Agents self-correct ~50% of the time when given explicit veto reasons.

**SDK constraint:**
- `max_rounds=2` default on AgentNodes in `coding_blueprint` (not unbounded)
- `on_max_rounds="escalate"` is the correct production default
- `JudgeNode` with `criteria` targeting scope creep is a validated use case, not theoretical
- `EscalationResult` is a feature, not a failure mode — returning to humans is the correct answer

---

## 4. MCP Tool Curation — Fewer Tools = Better Agents

MCP went from 100k downloads/month (Nov 2024) to 97M+ (early 2026) — 5,800+ servers. The ecosystem
is real. Stripe's internal Toolshed gives agents a curated subset of ~500 tools, scoped per task.
Anthropic's own research found that optimizing tool design had more impact on SWE-bench performance
than optimizing the overall system prompt.

No open-source SDK provides per-node tool curation with context window budgeting.

**SDK constraint:**
- `AgentNode.tools` is always a curated list — never pass all tools
- `mcp_tools("github", tools=["create_pr"])` — always name specific tools, never load all
- Keep `CODE_TOOLS`, `SHELL_TOOLS`, etc. as named subsets — not monolithic "all tools"
- Document this pattern prominently: "fewer tools = tighter context = more reliable agent behavior"

---

## 5. Rule Files: Scoped, Not Global

Stripe scopes rule files to subdirectories (per-module CLAUDE.md / AGENTS.md). Global rule dumps
cause token bloat and rule conflicts.

**SDK constraint:**
- CodeMinions' `_internal/rules.py` (RuleLoader) must support directory-scoped rules
- Never auto-inject all rules — load only rules relevant to the files being modified
- `AGENTS.md` at the repo root is the global spec; module-level files narrow scope

---

## 6. What Agents Actually Get Wrong (Real PR Data)

From a forensic audit of 33,596 real-world agent PRs:

1. CI failures from linting — each reduces merge probability ~15% (use `run_linter` with autofix before submit)
2. Scope creep — agents bundle refactors + new features (JudgeNode with scope criteria)
3. Silent error suppression — returning null instead of raising (test contracts matter)
4. Utility proliferation — reimplementing existing code (context files in Task reduce this)
5. Bad test mocks — mocked tests pass while integration breaks (real DB in DockerEnv is the answer)

From Columbia DAPLab's 9 failure patterns (Nov 2025):
- Business logic mismatch — runnable but semantically wrong
- API hallucination — placeholder credentials instead of requesting real ones
- Security vulnerabilities — 2.74x more XSS than human code

**SDK constraint:**
- `Task.acceptance` is mandatory for production tasks, not optional
- `Task.constraints` is the primary scope guard before JudgeNode
- `CI_TOOLS` should use real test environments, not mocks, wherever possible
- `ToolResult(recoverable=False)` is for security violations — escalate, don't retry

---

## 7. Unsolved Gaps (Track These)

From the 17-company case study, seven problems remain unsolved across the industry:

| Gap | Status | SDK relevance |
|-----|--------|--------------|
| Multi-repo dependencies | Unsolved | `GitWorktreeEnv` only handles single-repo |
| Agent handoff protocols | Partial | `state` sharing via Pydantic model is current answer |
| Cost governance | Unsolved | `token_budget` per node is partial; no org-level cap |
| Flaky test remediation evals | Unsolved | `CI_TOOLS` doesn't distinguish flaky from broken |
| Long-context reasoning (>200k tokens) | Active research | `token_budget` helps constrain; no full solution |
| Code review feedback capture | Unsolved | No primitive for feeding PR comments back to agent |
| Agent-generated code quality metrics | Unsolved | `JudgeNode` is qualitative; no quantitative scoring |

**SDK constraint:** Don't prematurely solve these. Build primitives that leave room for users to address
them — don't close off extension points trying to solve unsolved problems.

---

## 8. API Design Principles (from Anthropic Agent Patterns)

From Anthropic's internal agent guide (the research that informed Claude Code):

- Simplicity > complexity. The most effective systems are not the most complex.
- Composable patterns > frameworks. Expose primitives users can recombine.
- Tool design > system prompt. More time optimizing tools than the overall prompt paid off.
- Enough tokens to think: tools should return enough context for multi-step reasoning.
- Close to natural text: avoid forcing agents to learn new syntax for tool schemas.
- Avoid formatting overhead: no unnecessary XML or JSON wrapping in tool outputs.

**SDK constraint:**
- `@tool(description="...")` descriptions should be written for agent comprehension, not human docs
- Tool output should be prose-friendly — not raw JSON the agent has to re-parse
- `ToolOutputPolicy.max_chars = 50_000` is intentionally generous — don't truncate reasoning context
- When in doubt, make the tool do more work (clean output) not the agent (parse output)

---

## References

| Source | Key Insight |
|--------|------------|
| Stripe Minions Part 1 & 2 | Blueprint hybrid, 2-CI-round cap, pre-warmed devboxes |
| arxiv:2508.02721 | Academic validation of deterministic+agent hybrid pattern |
| Spotify Honk (Dec 2025) | JudgeNode with 25% veto rate; constrained tools = predictability |
| Factory.ai Linters for Agents | Lint green = definition of Done |
| Columbia DAPLab (Nov 2025) | 9 failure patterns from real deployments |
| Forensic audit of 33,596 PRs | Real merge probability data |
| Penligent.ai worktree isolation | Why code isolation ≠ runtime isolation |
| MCP Adoption Statistics (2026) | 97M+ downloads/month, 5,800+ servers |
| Anthropic Agent Guide (internal) | Tool design > prompt design |
| Open SWE / LangChain convergence (Mar 2026) | Industry converging on Blueprint hybrid |
