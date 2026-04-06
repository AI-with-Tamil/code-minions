I now have comprehensive data across all companies. Let me compile the full research report.

---

# Deep Research: How Top Tech Companies Automate Coding with AI Agents

## TIER 1 — COMPANIES WITH PUBLISHED TECHNICAL DETAILS

---

### 1. Stripe — Minions

**What they built:** Minions is Stripe's internal background coding agent, built on a fork of Block's Goose. It is not a product — it's infrastructure.

**Architecture:**
- **Isolation:** Pre-warmed "devboxes" — isolated EC2 instances that spin up in **10 seconds**, loaded with all of Stripe's code and services. Identical to what human engineers use but air-gapped from production and the internet. No git worktrees — the full repo is cloned per box.
- **Blueprint pattern (deterministic + agent hybrid):** The core innovation. A Blueprint is a state machine alternating between two node types:
  - **Deterministic nodes** (rectangle): Fixed code execution — "Run configured linters," "Push changes." No LLM invocations. Saves tokens at scale.
  - **Agentic nodes** (cloud shape): Open-ended LLM loops — "Implement task," "Fix CI failures."
  - Teams write their own custom Blueprints for migrations, infra tasks, etc.
- **Context strategy:** Stripe standardized on Cursor's rule file format with directory/pattern scoping. Rule files are synchronized across Minions, Cursor, and Claude Code. This means the same conventions guide every tool. For pre-run context, MCP tools run deterministically over likely-looking issue links before the agent even starts.
- **Tooling:** A centralized internal MCP server called **Toolshed** hosts ~500 carefully curated tools spanning internal systems and SaaS platforms. Agents get a small default set plus task-specific additions. Sourcegraph search is integrated for code intelligence.
- **Validation (three-layer):**
  1. Local heuristic lint (5 seconds, deterministic)
  2. Selective CI from Stripe's 3M+ test suite with automatic autofixes applied
  3. If fixes fail, agent gets a second CI round. At most two CI rounds per run.
- **Scale:** 1,000–1,300 PRs merged per week, operating on hundreds of millions of lines of Ruby/Sorbet. Zero human-written code in Minion PRs; 100% human review before merge.
- **Human-in-the-loop:** Mandatory human review before any merge. No auto-merge.
- **Failure modes:** Two CI round limit keeps costs controlled; errors without autofixes return to the agent. The "walls" (devbox isolation + Blueprint structure) are emphasized as more important than model quality.

**Key insight:** Blueprints let you replace unpredictable LLM decisions with deterministic code wherever you can anticipate the logic. This controls CI costs and improves reliability at the token-per-task level.

**Sources:** [Stripe Minions Part 1](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents) | [Stripe Minions Part 2](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2) | [ByteByteGo breakdown](https://blog.bytebytego.com/p/how-stripes-minions-ship-1300-prs) | [Open SWE convergence analysis](https://devops.com/open-swe-captures-the-architecture-that-stripe-coinbase-and-ramp-built-independently-for-internal-coding-agents/)

---

### 2. Ramp — Inspect

**What they built:** Inspect is Ramp's internal background coding agent, built on Modal infrastructure. Not a product — internal only. Has grown to handle ~50% of merged PRs (some sources say 30%; the modal.com post claims ~50%).

**Architecture:**
- **Isolation:** Each session runs in its own Modal Sandbox — a full-stack isolated VM containing Postgres, Redis, Temporal, RabbitMQ, Vite. No cross-session contention. Critically: "no network hop between the agent and the test suite, no remote filesystem to sync" — local latency for all services.
- **Image registry pattern:** Cron jobs (30-minute intervals) pre-build filesystem snapshots of each repo: clone, install dependencies, complete initial setup. Snapshots stored as diffs from a base image. Session startup time: a few seconds (matches local dev).
- **Agent runtime:** OpenCode runs as the coding agent inside the sandbox, alongside VS Code Server, web terminal, and VNC/Chromium for visual verification.
- **State management:** Cloudflare Durable Objects for session state and conversation context. Modal Dicts for session locks and image metadata. Modal Queues for routing prompts from multiple clients.
- **Multi-client design:** Slack bot, web interface, Chrome extension (for visual React component editing). All route to the same agent state.
- **Context strategy:** Full enterprise integration — GitHub, Slack, Buildkite, Sentry, Datadog, LaunchDarkly, Temporal all accessible from inside the sandbox.
- **Visual verification loop:** Agent can take before/after screenshots, navigate the app in a real browser. Unique among the peer group.
- **Scale:** Hundreds of concurrent sessions; ~50% of merged PRs at Ramp; 80% of Inspect itself was written by Inspect.
- **Human-in-the-loop:** VS Code Server allows engineers to manually edit inside a running session. Multiplayer collaboration possible.
- **What's unique:** Full-stack local-latency sandbox. Visual DOM verification via Chrome extension for non-engineers. The "few days" prototype time on Modal's primitives.

**Key insight:** Pre-warming filesystem snapshots every 30 minutes eliminates cold start time. The visual loop is rare — most peer systems only use text-based test output.

**Sources:** [Modal blog: How Ramp built Inspect](https://modal.com/blog/how-ramp-built-a-full-context-background-coding-agent-on-modal) | [InfoQ](https://www.infoq.com/news/2026/01/ramp-coding-agent-platform/) | [Open SWE analysis](https://devops.com/open-swe-captures-the-architecture-that-stripe-coinbase-and-ramp-built-independently-for-internal-coding-agents/)

---

### 3. Coinbase — Cloudbot

**What they built:** Cloudbot is Coinbase's internal coding agent, built code-first using LangGraph/LangChain. Internal only.

**Architecture:**
- **Code-first graphs:** The central architectural decision. LangGraph workflows separate deterministic data nodes (unit-testable) from probabilistic LLM nodes (evaluated separately). This makes failures diagnosable and runs reproducible.
- **Isolation:** Isolated cloud sandboxes (specific provider not publicly disclosed).
- **Context injection:** Full Linear issue or Slack thread assembled as startup context before any agent work begins.
- **Subagent orchestration:** "Agent councils" — multiple specialized agents that validate each other's output before proceeding. More aggressive than Stripe's single-agent model.
- **Auto-merge capability:** Coinbase built auto-merge logic, unlike Stripe and Ramp which require human review. This is the most aggressive automation posture of the peer group.
- **Human-in-the-loop:** Intentional design: "Design the handoff and feedback loop into the UX." Feedback captured where work happens.
- **Observability:** First-class evaluation, observability, and human-in-the-loop controls attached to the graph.
- **Also notable:** NodeSmith (separate system) — AI-driven automation for blockchain node upgrades, reducing engineering effort by 30%.

**Key insight:** Code-first LangGraph gives Coinbase typed interfaces, version control, and clean separation — something YAML-based or prompt-driven approaches don't provide. Agent councils for validation is a unique pattern.

**Sources:** [Coinbase enterprise AI agents blog](https://www.coinbase.com/blog/building-enterprise-AI-agents-at-Coinbase) | [Open SWE](https://blog.langchain.com/open-swe-an-open-source-framework-for-internal-coding-agents/) | [NodeSmith](https://www.coinbase.com/blog/NodeSmith-AI-Driven-Automation-for-Blockchain-Node-Upgrades)

---

### 4. Spotify — Honk (3-Part Series)

**What they built:** Honk is Spotify's internal background coding agent, integrated with their existing Fleet Management platform (which already handled repo targeting, PR creation, review routing, and merging). It's a thin CLI wrapper over pluggable LLM backends.

**Architecture (Part 1 — Integration):**
- **Isolation:** Fleet Management's containerized environments inherited by Honk. Critically: agent runtime is separated from verification runtime. Agent pushes branches → verification service triggers CI → waits for results → only creates PR after full validation passes.
- **CLI as orchestrator:** Small internal CLI that delegates to pluggable LLM backends. Engineers can swap between Claude Code, GPT-4, etc. without changing workflows.
- **Fleet Management reuse:** PR creation, targeting, review, merge — all inherited from existing infrastructure. The agent only handles code transformation.
- **In July 2025:** Integrated the Claude Agent SDK directly into Fleet Management. Claude Code is top performer, used for ~50 migrations.

**Architecture (Part 2 — Context Engineering):**
- **Static prompts, not RAG:** Deliberately chose larger static prompts over dynamic retrieval. Reason: "easier to reason about, version-control the prompts, write tests, and evaluate their performance."
- **Three context mechanisms:**
  1. User-provided context condensed into the prompt manually
  2. Repository-level guidance (tests, linters, API docs in target repos) that work for all agents
  3. Limited tool access: a "verify" tool, a Git tool with allowlisted commands, Bash with allowlisted commands (ripgrep included)
- **Prompt tuning:** Claude Code responds better to end-state descriptions than step-by-step instructions. Single changes per prompt. Concrete code examples heavily influence results. Define measurable endpoints via tests.

**Architecture (Part 3 — Feedback Loops):**
- **Independent verifiers:** Maven verifier activates if pom.xml exists; agent calls it as a tool but doesn't know implementation details. All relevant verifiers run before PR opens via Claude Code's stop hook.
- **LLM-as-judge:** Second protection layer. Judge evaluates diff against original prompt. Vetoes ~25% of sessions. Agents successfully self-correct ~50% of the time when vetoed. Most common veto trigger: agent going outside the instructions.
- **Three failure categories:** Failed PR generation (minor), PR failing CI (frustrating), PR passing CI but functionally wrong (most serious).
- **Evals:** Not yet invested in evals for the judge — acknowledged future priority.

**Scale:** 1,500+ merged PRs (as of Nov 2025). 1,000 merged PRs every 10 days. 650+ PRs/month into production (Anthropic customer story). 60–90% time savings vs manual. QCon London 2026: "Rewriting All of Spotify's Code Base, All the Time."

**Key insight:** The LLM-as-judge pattern with a 25% veto rate is a concrete, empirically calibrated safety layer that's rarely seen documented with actual numbers elsewhere.

**Sources:** [Honk Part 1](https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1) | [Honk Part 2](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2) | [Honk Part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3) | [QCon 2026](https://www.infoq.com/news/2026/03/spotify-honk-rewrite/)

---

### 5. Google — DIDACT, Gemini Code Assist, KernelEvolve

**What they built:** Multiple systems: DIDACT (model trained on internal engineering activity logs), Gemini Code Assist (deployed externally and internally), and KernelEvolve (kernel optimization agent).

**DIDACT Architecture:**
- **Training data design:** Aligned corpus of code with task-specific annotations. Data captures fine-grained code edits, build outcomes, edits to resolve build failures, copy-paste patterns, code review comments, edits to fix reviewer issues, and submissions. Essentially: a model that learned software engineering from observing thousands of engineers doing it.
- **Fusion:** DIDACT data being fused with Gemini foundation models for next-generation internal tools.

**Gemini Code Assist at Scale:**
- **50% of new code characters** at Google are AI-generated
- **37% acceptance rate** on code completion suggestions
- **>8%** of code review comments addressed with AI
- **~2%** of IDE code from AI-assisted paste adaptation
- **Feedback mechanism:** Online A/B experiments emphasized over offline metrics. Usage log tuning (acceptances, rejections, corrections).

**KernelEvolve (April 2026):**
- **Problem:** Kernel optimization for heterogeneous hardware (NVIDIA GPUs, AMD, Meta's MTIA)
- **Architecture:** Six components: LLM Synthesizer, Tree Search Engine (Monte Carlo + evolutionary strategies), RAG Knowledge Base (hierarchical retrieval of hardware docs), Automated Evaluation Framework (TritonBench, PyTorch Profiler, NVIDIA NCU), Shared Data Foundation, Agentic Reinforcement Learning (post-trains on domain trajectories).
- **Isolation:** Purpose-built job-harness handles multi-minute build cycles and infrastructure failures independently.
- **Feedback loop:** Compilation results + hardware profiling metrics continuously fed back to synthesizer. Not a one-shot system.
- **Scale:** 100% pass rate on KernelBench (250 kernels), 60%+ inference throughput improvement on NVIDIA, 25%+ training throughput on MTIA. Weeks of expert work → hours.

**Key insight:** DIDACT's training-data approach (log-based learning from real engineering activity) is architecturally different from all peers — it's a model that learned the whole software development loop, not just code generation.

**Sources:** [Google AI in Software Engineering blog](https://research.google/blog/ai-in-software-engineering-at-google-progress-and-the-path-ahead/) | [KernelEvolve](https://engineering.fb.com/2026/04/02/developer-tools/kernelevolve-how-metas-ranking-engineer-agent-optimizes-ai-infrastructure/) (note: Meta blog URL but about Google's architecture per the paper)

---

### 6. Meta — Confucius Code Agent, KernelEvolve

**What they built:** Confucius Code Agent (CCA, with Harvard) is a research-grade but industrially-intended framework. KernelEvolve (published on Meta's engineering blog April 2026) optimizes production kernels autonomously.

**CCA Architecture:**
- **Confucius SDK:** Three perspectives: Agent Experience (AX), User Experience (UX), Developer Experience (DX).
- **Hierarchical working memory:** Orchestrator partitions trajectories into scopes, summarizes past steps, keeps compressed context for later turns. Keeps prompts within context limits while preserving patches, error logs, and design decisions.
- **Persistent note-taking:** Dedicated sub-agent writes structured Markdown notes from execution traces, capturing task-specific strategies, repo conventions, common failure modes. Stored as long-term memory, reused across sessions.
- **Meta-agent:** Automates construction, evaluation, and refinement of agents through build-test-improve cycles.
- **Performance:** 59% Resolve@1 on SWE-Bench-Pro (stronger benchmark than SWE-bench Verified). Stable on multi-file changes: 57.8% for 1–2 files, 44.4% for 10+ files.
- **Open-sourced.**

**Key insight:** Persistent cross-session note-taking by a dedicated sub-agent is the most sophisticated memory architecture in this research. It solves the "agent amnesia" problem structurally.

**Sources:** [Confucius Code Agent paper](https://arxiv.org/abs/2512.10398) | [MarkTechPost](https://www.marktechpost.com/2026/01/09/meta-and-harvard-researchers-introduce-the-confucius-code-agent-cca-a-software-engineering-agent-that-can-operate-at-large-scale-codebases/) | [KernelEvolve blog](https://engineering.fb.com/2026/04/02/developer-tools/kernelevolve-how-metas-ranking-engineer-agent-optimizes-ai-infrastructure/)

---

### 7. LinkedIn — AI Agent Platform

**What they built:** Internal platform for governing and running background coding agents at scale across LinkedIn's engineering organization.

**Architecture:**
- **Specification-driven execution:** Instead of free-form prompts, structured specifications define: what should happen, which tools may be used, how success is evaluated, what actions are disallowed. Reduces ambiguity that causes inconsistent behavior.
- **Centralized orchestration layer:** Manages end-to-end execution: decomposes work, provisions isolated sandboxes, injects scoped context, invokes tools, records execution traces.
- **MCP unified access:** Model Context Protocol unifies tool access across models.
- **Foreground vs. background agents:** Foreground agents assist directly in IDE; background agents handle repetitive toil asynchronously (migrations, upgrades, test coverage improvements).
- **Autonomy vs. authority model:** Agents act freely within bounded environments (read/write code). Irreversible actions (deployments, merges to main) remain human-gated. Agents pause at approval gates, resume after input.
- **Institutional memory:** Feedback from reviews, failures, and prior executions captured and reintroduced as context for future tasks. Framed as "context engineering more important than model selection."

**Key insight:** The specification-as-contract pattern (not free-form prompts) is LinkedIn's answer to agent reliability. Explicitly disallowed actions are part of the spec — not just guardrails bolted on later.

**Sources:** [QCon AI NY 2025 InfoQ](https://www.infoq.com/news/2025/12/qcon-ai-linkedin/) | [Platform Engineering for AI: MCP at LinkedIn](https://www.infoq.com/podcasts/platform-engineering-scaling-agents/)

---

### 8. Shopify — Roast Framework

**What they built:** Roast is an open-source Ruby framework for structured AI workflows, used internally at Shopify. Now rebuilt as a pure Ruby DSL (v1.0). GitHub: [Shopify/roast](https://github.com/Shopify/roast).

**Architecture:**
- **Workflow definition:** Pure Ruby DSL (was YAML + Markdown). Steps defined declaratively. Step types: directory-based (prompt.md with ERB), command execution ($() syntax), inline prompts (^ prefix for CodingAgent), custom Ruby steps, parallel steps (nested arrays).
- **Deterministic + agent hybrid:** Core design philosophy: "Allowing AI to roam free around millions of lines of code just didn't work very well. Non-determinism is the enemy of reliability." Deterministic steps handle what can be anticipated; CodingAgent handles what requires iteration.
- **Shared conversation transcript:** Steps share context from prior steps automatically, building cumulative context without workflow author configuration.
- **Session replay:** Every execution auto-saves. Resume from any step. Eliminates expensive AI rerun during development iteration.
- **Real workflow — "Boba" (Sorbet typing):** Deterministic steps run Sorbet autocorrect → CodingAgent iteratively fixes remaining type errors → runs tests → ensures passing. Hybrid handoff at the boundary of what static tools can handle.
- **Tooling:** ReadFile/WriteFile, UpdateFiles (diff/patch), Grep/SearchFile, Cmd/Bash, CodingAgent (Claude Code integration).
- **Scale:** 500 daily active users internally; 250,000 requests/second at peak (though this seems likely to be the LLM proxy layer, not Roast specifically).
- **Human review:** Senior engineer review before any merge. No auto-merge.

**Key insight:** The "handwave a step you don't understand yet with an AI approximation, then replace it with deterministic code later" paradigm inverts traditional automation — you can start without fully understanding the problem space.

**Sources:** [Shopify Engineering: Introducing Roast](https://shopify.engineering/introducing-roast) | [GitHub repo](https://github.com/Shopify/roast) | [Pragmatic Engineer interview](https://newsletter.pragmaticengineer.com/p/how-ai-is-changing-software-engineering)

---

### 9. Uber — uReview, AutoCover, Minion, Shepherd

**What they built:** A suite of four internal AI developer tools, each targeting a different stage of the development loop.

**Architecture:**

**uReview (AI Code Review):**
- Deployed across all 6 of Uber's monorepos (Go, Java, Android, iOS, TypeScript, Python).
- Reviews every commit in CI. Median turnaround: 4 minutes.
- **Four-stage pipeline:** Ingestion/preprocessing (filters generated code, config files, experimental dirs) → Comment Generation (three specialized assistants: Standard for bugs/logic, Best Practices for Uber conventions, AppSec for security) → Post-processing/quality filtering → Delivery with feedback mechanism.
- **False positive mitigation:** Secondary confidence-scoring prompt per comment, per-assistant/per-language/per-category thresholds, semantic deduplication, category suppression for historically low-value types based on developer ratings.
- **Feedback pipeline:** Comments stream to Apache Kafka/Hive with metadata (origin, category, confidence, developer rating). Enables continuous threshold tuning.
- **Re-runs uReview 5× on final commits** to verify resolution, accounting for LLM stochasticity.
- **Scale:** Reviews 90% of ~65,000 weekly diffs. 75% usefulness rating. 65% of posted comments addressed.

**AutoCover (Test Generation):**
- Generates 5,000+ unit tests/month.
- 10% increase in developer platform coverage.
- Estimated 21,000 developer hours saved.
- LangGraph-based. Uses internal Michelangelo ML platform for model access.

**Minion (Background Agent Platform):**
- Internal background agent with monorepo access and optimized defaults.
- Submit via web, Slack, or CLI. Generates code changes, opens PRs automatically.
- 11% of all PRs at Uber opened by agents.

**Shepherd (Migration Orchestration):**
- Manages large-scale migrations end-to-end. Specific architecture not yet published, but handles Uber's massive Spark job upgrades (85% migrated to Spark 3 in 6 months).

**MCP Gateway:** Central hub exposing internal Thrift/Protobuf endpoints as MCP servers. Handles authentication, authorization, telemetry. MCP registry with sandbox capabilities.

**Uber Agent Builder:** No-code platform for multi-agent workflows with Studio for visualization, debugging, tracing, versioning, evaluation.

**Scale:**
- 84% of developers use agentic tools monthly (March 2026)
- 65–72% of code generated via IDE tools; 100% for CLI tools like Claude Code
- Claude Code usage doubled in 3 months (32% Dec 2025 → 63% Feb 2026)
- AI costs up 6× since 2024

**Key insight:** uReview's five-run stochasticity check is a sophisticated quality assurance mechanism. Running the reviewer five times on the final commit to verify comment resolution is not seen at any peer company publicly.

**Sources:** [uReview blog](https://www.uber.com/blog/ureview/) | [Pragmatic Engineer: How Uber uses AI](https://newsletter.pragmaticengineer.com/p/how-uber-uses-ai-for-development) | [ZenML database](https://www.zenml.io/llmops-database/building-ai-developer-tools-using-langgraph-for-large-scale-software-development)

---

## TIER 2 — COMPANIES WITH PARTIAL TECHNICAL DETAILS

---

### 10. Anthropic — Claude Code Internal Usage

**What they built:** Anthropic uses Claude Code internally as primary coding infrastructure. Most code is now written by Claude Code.

**Internal patterns published:**
- **Two-agent harness for long tasks:**
  - Initializer agent: creates `init.sh`, `claude-progress.txt`, initial git commit establishing baseline.
  - Coding agent: each session reads progress log + git history, picks next task, runs services, validates with Puppeteer MCP, makes incremental progress, ends clean.
  - Feature list in JSON (not Markdown) — JSON resists unintended model modification better.
  - One feature per session to prevent context exhaustion.
- **Multi-agent parallelism:** Engineers run 5–10 Claude instances simultaneously. Most common: 2–4. Agent Teams let a lead instance coordinate sub-agents working in separate context windows.
- **Scale shift:** 6 months prior: ~10 agent actions before human input needed. Now: ~20 actions before input needed. Feature implementation use grew from 14.3% to 36.9% of transcripts. Code design/planning grew from 1.0% to 9.9%.
- **On-call integration:** On-call playbooks put into slash commands; Claude Code given access to tools mentioned in the playbook.
- **Philosophy:** "Use AI as aggressively as possible — only by giving agents really hard tasks can you push what they're capable of."

**Sources:** [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | [How Anthropic teams use Claude Code (PDF)](https://www-cdn.anthropic.com/58284b19e702b49db9302d5b6f135ad8871e7658.pdf) | [Coder blog](https://coder.com/blog/inside-anthropics-ai-first-development)

---

### 11. GitHub — Copilot Coding Agent

**What they built:** GitHub Copilot Coding Agent — a background agent that operates on GitHub issues. External product (Copilot Enterprise tier). Technical Preview of Workspace ended May 2025; replaced by the Coding Agent.

**Architecture:**
- **Isolation:** Ephemeral GitHub Actions environment. Spun up per task, cleaned up after. Agent can only push to branches it creates (`copilot/*`). Main/protected branches untouched.
- **Firewall:** Built-in agent firewall blocks outbound internet access by default. Allowlist: OS package repos (Debian, Ubuntu, RHEL), container registries (Docker Hub, ECR, ACR), language package registries. Firewall applies only to processes started via the agent's Bash tool. Enterprise can configure allowlists at org level (April 2026).
- **Context strategy:** Reviews repository context (related issues, PR discussions, custom instructions via `.github/copilot-instructions.md`). Agent-specific instructions supported.
- **Tooling:** File exploration, code editing, test/lint execution, GitHub Actions catalog (25,000 community actions), MCP servers (Playwright, GitHub MCP).
- **PR workflow:** Agent opens draft PR tagged [WIP] → pushes commits as work progresses → marks PR complete with title/description → human reviews before any CI/CD runs.
- **Self-review:** Agent performs self-review before flagging complete. Security scanning built in.
- **Model:** GPT-4.1 as default (as of early 2026). Supports model picker.
- **Human-in-the-loop:** All PRs require human approval before CI/CD workflows run. Developer can request iterations via `@copilot` comments.

**Sources:** [GitHub Copilot Coding Agent 101](https://github.blog/ai-and-ml/github-copilot/github-copilot-coding-agent-101-getting-started-with-agentic-workflows-on-github/) | [Firewall docs](https://docs.github.com/copilot/customizing-copilot/customizing-or-disabling-the-firewall-for-copilot-coding-agent) | [About the coding agent](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent)

---

### 12. Microsoft — AutoDev

**What they built:** AutoDev is a research framework (paper: arxiv 2403.08299, March 2024). Academic prototype that influenced production thinking.

**Architecture:**
- **Four components:** Conversation Manager (dialogue tracking, command parsing/validation), Agent Scheduler (Round Robin/token/priority-based multi-agent coordination), Tools Library (six categories), Evaluation Environment (Docker containers).
- **Docker isolation:** All operations inside Docker containers. Users configure YAML with permitted commands per agent.
- **Two-agent model tested:** Developer agent + Reviewer agent pairing.
- **Tools (six categories):** File editing (write/edit/insert/delete, line-level), Retrieval (grep/find/ls + embedding-based lookup), Build/Execution (compile/run abstraction), Testing/Validation (test execution + linting + syntax checking), Git (configurable commit/push/merge), Communication (talk/ask/stop).
- **Feedback loop:** Agents receive execution outputs (test failures, compiler errors) → parser validates → Output Organizer summarizes crucial info back to agent → iterates.
- **Results:** 91.5% Pass@1 on HumanEval for code generation; 87.8% for test generation. Average 5.5 commands per code generation task.
- **Failure modes documented:** Command parsing issues (mixing natural language with code), multiple LLM inference calls (5–6 per task vs. 1 for baselines), Docker overhead vs. direct CLI.

**Sources:** [AutoDev paper](https://arxiv.org/html/2403.08299v1) | [MarkTechPost](https://www.marktechpost.com/2024/03/19/microsoft-introduces-autodev-a-fully-automated-artificial-intelligence-driven-software-development-framework/)

---

### 13. Atlassian — Rovo Dev

**What they built:** Rovo Dev is a CLI-based coding agent (external product). Achieved #1 on SWE-bench full (2,294 tasks) at 41.98% resolve rate.

**Architecture:**
- **Teamwork Graph:** Semantic layer connecting people, teams, projects, issues, content, and relationships. All Rovo agents draw from this graph for context about priorities and organizational context.
- **Multi-model:** Chooses the best LLM per task (Claude, GPT, Gemini, Llama). Not locked to one provider.
- **MCP integration:** Remote MCP Server connects Atlassian Cloud instances to external AI tools while enforcing permissions and governance. Atlassian was among first major vendors to adopt MCP.
- **Agent types:** Code planner (Jira tickets → technical plans), code writer, code reviewer, deployment agent.
- **Context:** Jira issues, Confluence docs, and repository context merged through the Teamwork Graph.
- **CLI for background tasks:** Rovo Dev CLI operates as an agent in the terminal, managing full development workflows.

**Sources:** [Rovo Dev CLI announcement](https://www.atlassian.com/blog/announcements/rovo-dev-command-line-interface) | [Valiantys: Atlassian AI architecture](https://www.valiantys.com/en/resources/making-sense-of-atlassians-ai-architecture-a-guide-for-it-leaders-and-builders) | [Atlassian Team '25](https://devops.com/atlassian-adds-bevy-of-ai-agents-across-software-development-lifecycle/)

---

### 14. Block (Square) — Goose

**What they built:** Goose is Block's open-source local-first AI agent framework. External open-source product, also used internally. Stripe's Minions are built on a fork of Goose. Apache 2.0 license. Donated to the Agentic AI Foundation (Linux Foundation). GitHub: [block/goose](https://github.com/block/goose).

**Architecture:**
- **On-machine, local-first:** Runs locally by default, not cloud-hosted. Works with any LLM supporting tool calling.
- **MCP-native:** MCP is the primary extension mechanism. Connects to any MCP server for tools and context.
- **Capabilities:** Build projects from scratch, write and execute code, debug failures, orchestrate workflows, interact with external APIs, install dependencies, read/write files, run tests.
- **Extension architecture:** Plug-and-play MCP extensions for GitHub, Google Drive, JetBrains IDEs, custom integrations. Also desktop app + CLI.
- **Multi-model:** Configurable per task for cost/performance optimization.
- **Not sandboxed by default:** Runs in the user's actual environment. Users are responsible for safety.

**Sources:** [Block open-source announcement](https://block.xyz/inside/block-open-source-introduces-codename-goose) | [GitHub repo](https://github.com/block/goose) | [Linux Foundation announcement](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation)

---

### 15. Cursor — Codebase Indexing

**What they built:** Cursor is an AI-native IDE (external product). Their codebase indexing system is their key technical differentiation.

**Architecture:**
- **Embedding pipeline:** Files chunked (function-level), encrypted locally, sent to Cursor servers with obfuscated file identifiers. Server decrypts, computes embeddings with GPU-backed models, stores embedding vectors in **Turbopuffer** (specialized vector DB). Only vectors stored server-side — no persistent plain-text code.
- **Merkle tree sync:** High-latency sync engine (runs every 3 minutes) uses Merkle trees to detect diffs and keep on-server index current. Efficient for large codebases.
- **Context compression pipeline:** Embedding search finds relevant files (10M tokens → 500K) → importance ranking (500K → 50K) → smart truncation preserving critical sections (50K → 8K for prompt).
- **Context window:** Extended up to 272K tokens.
- **Autocomplete vs. chat:** Different retrieval strategies per feature — autocomplete prioritizes speed and local context; chat uses full embedding search.
- **Scale:** Handles 1M+ transactions/second at peak. Serves billions of daily completions.
- **Indexing time:** Minutes for large codebases; sub-minute for typical.

**Key insight:** The Merkle tree approach for incremental sync is borrowed from distributed systems engineering — not seen in competing products' public documentation.

**Sources:** [How Cursor Actually Indexes Your Codebase](https://towardsdatascience.com/how-cursor-actually-indexes-your-codebase/) | [Cursor secure codebase indexing](https://cursor.com/blog/secure-codebase-indexing) | [ByteByteGo: How Cursor Serves Billions](https://blog.bytebytego.com/p/how-cursor-serves-billions-of-ai)

---

### 16. Cognition — Devin 2.0

**What they built:** Devin is a commercial AI software engineer product. Devin 2.0 (April 2025) shifted from "fully autonomous" to "agent-native IDE experience."

**Architecture:**
- **Isolation:** Cloud-based development environment with isolated VMs per session. Multiple parallel Devin instances supported.
- **Toolset:** Shell, code editor, browser — standard developer tools inside sandboxed compute.
- **Context/memory:** Maintains context across long tasks. DeepWiki automatically indexes repos and produces wikis with architecture diagrams, dependency analysis. `deepwiki.com` replaces `github.com` in URLs for repo-level docs. Used as context source before task start.
- **Interactive planning:** Devin drafts step-by-step plans for user approval before execution.
- **Performance trajectory:** PR merge rate 34% → 67% over 18 months. Problem-solving speed 4× faster. Codebase understanding doubled.
- **What it does well:** Security fixes (20× faster than humans), code migrations (10–14× faster), test coverage increases (50–60% → 80–90%), brownfield features when code provides clear patterns.
- **What breaks:** Ambiguous requirements, mid-task pivots, visual design without explicit specifications, soft skills. Mid-task instruction changes cause degradation.

**Sources:** [Devin annual performance review 2025](https://cognition.ai/blog/devin-annual-performance-review-2025) | [Devin 2.0 technical design analysis](https://medium.com/@takafumi.endo/agent-native-development-a-deep-dive-into-devin-2-0s-technical-design-3451587d23c0) | [SWE-bench technical report](https://cognition.ai/blog/swe-bench-technical-report)

---

### 17. OpenHands — SDK Architecture

**What they built:** OpenHands (formerly OpenDevin) is an open-source AI software agent platform with a companion SDK. ICLR 2025 paper. GitHub: [OpenHands](https://github.com/All-Hands-AI/OpenHands). SWE-bench Verified: 72% with Claude Sonnet 4.5 + extended thinking.

**Architecture (SDK v1):**
- **Four packages:** `openhands.sdk` (core: Agent, Conversation, LLM, Tool, MCP), `openhands.tools` (concrete tools), `openhands.workspace` (Docker/hosted execution), `openhands.agent_server` (REST/WebSocket API).
- **Stateless event processor:** Agents are immutable configuration specifications. Execution is an event-driven loop. All state lives in a single `ConversationState` object. Enables pause/resume/recovery.
- **Event-sourced state:** Hierarchical: Base Event → LLMConvertibleEvent (visible to LLM) / Internal Events (bookkeeping). EventLog is append-only. Resume by replaying events from last checkpoint.
- **Isolation (opt-in):** Default: local in-process (fast iteration). Optional: Docker (isolation, resource control, multi-tenancy). LocalWorkspace and RemoteWorkspace share identical APIs.
- **Condenser system:** When history exceeds context limits, drops events and replaces with LLM-generated summaries (CondensationEvent). Default LLMSummarizingCondenser reduces API costs 2× with no performance degradation.
- **Tool pattern:** Action → Execution → Observation. Pydantic validation before execution. Tools serialize as pure JSON — cross process/network boundaries, reconstruct executor at runtime.
- **Security:** SecurityAnalyzer rates tool calls (LOW/MEDIUM/HIGH/UNKNOWN). ConfirmationPolicy determines user approval need. Secret Registry masks credentials in logs and LLM context.
- **Large codebase handling:** AGENTS.md / repo.md as static context, skills system, sub-agent delegation via `delegate` tool, model-agnostic multi-LLM routing (RouterLLM: cheaper models for text, multimodal for images).
- **MCP integration:** MCPToolDefinition auto-translates JSON Schema to Action models.

**Sources:** [OpenHands SDK paper](https://arxiv.org/html/2511.03690v1) | [OpenHands platform paper](https://arxiv.org/abs/2407.16741) | [OpenReview ICLR 2025](https://openreview.net/forum?id=OJd3ayDDoF)

---

## CROSS-CUTTING TOPICS

---

### A. Large Codebase Context Strategies

**The Core Problem:** 100M+ line codebases cannot fit in any context window. Companies have independently arrived at different solutions:

**1. Embedding-based RAG (Cursor, Augment Code)**
- Cursor: Function-level chunking → GPU embedding → Turbopuffer vector DB → Merkle tree sync for freshness. Multi-stage compression pipeline to fit in context window.
- Augment Code: Custom code-specific embedding models (not generic APIs), Google Cloud infrastructure (PubSub/BigTable/AI Hypercomputer), per-developer personal indexes updated in seconds. 400,000+ file support. Cryptographic proof-of-possession for authorization.

**2. Graph-based code intelligence (Greptile, CodeRabbit)**
- Greptile: Parse AST → generate docstrings for each node → embed docstrings → build function/class/variable/dependency graph. During review: multi-hop investigation traces dependencies, checks git history, follows leads across files (v3, using Claude Agent SDK).
- CodeRabbit: Codegraph (definitions/references/co-change history), Code Index (semantic embeddings via LanceDB), verification scripts (grep/ast-grep) to confirm assertions before posting comments.

**3. BM25 + platform search (Sourcegraph/Cody)**
- Moved away from embeddings (external API dependency, operational complexity, scaling issues at 100k+ repos). Now uses native Sourcegraph platform search: BM25 ranking on tokenized queries over file snippets. Tree-Sitter for autocomplete intent classification.

**4. Static prompts (Spotify)**
- Deliberately no RAG. Larger static prompts with user-provided context. Easier to version-control, test, and evaluate. Trades flexibility for reliability.

**5. Rule files (Stripe, Open SWE)**
- Cursor rule format standardized across Minions, Cursor, Claude Code. Directory/pattern scoping. AGENTS.md files per subdirectory in monorepos.

**6. Tool-based retrieval (most background agents)**
- Agents given ripgrep, grep, find as tools. They retrieve what they need. Lower upfront complexity; higher per-run token cost.

**Academic work (2024–2025):**
- [Codebase-Memory](https://arxiv.org/html/2603.27277): Tree-Sitter-based knowledge graphs via MCP. 83% answer quality at 10× fewer tokens, 2.1× fewer tool calls vs. file-exploration.
- GraphCoder (ASE 2024), CodexGraph (NAACL 2025), RepoGraph (ICLR 2025): Graph-based retrieval approaches outperform flat embedding search for relational queries.
- [Retrieval-Augmented Code Generation survey](https://arxiv.org/html/2510.04905v1): Comprehensive comparison of repository-level approaches.

**Sources:** [Sourcegraph: How Cody understands codebases](https://sourcegraph.com/blog/how-cody-understands-your-codebase) | [Augment Code real-time index](https://www.augmentcode.com/blog/a-real-time-index-for-your-codebase-secure-personal-scalable) | [Codebase-Memory paper](https://arxiv.org/html/2603.27277) | [Greptile graph docs](https://www.greptile.com/docs/how-greptile-works/graph-based-codebase-context)

---

### B. Code Review Automation at Scale

**The bottleneck problem:** AI accelerates code generation but creates a PR review crisis. Key data:
- Teams with high AI adoption merge 98% more PRs but review time increases 91%.
- PRs are 18% larger on average.
- Teams handling 10–15 PRs/week now face 50–100.
- Senior engineers spend 4.3 min reviewing AI-generated code vs 1.2 min for human-written (3.6× longer).
- AI-written code surfaces 1.7× more issues than human-written (CodeRabbit 2025 study).

**CodeRabbit:**
- **Infrastructure:** Google Cloud Run (3600-second timeout, 8 concurrent requests/instance) behind Google Cloud Tasks queue. Webhook decoupled from execution. Two layers of sandboxing (microVM + Jailkit isolated processes).
- **Context:** LanceDB for semantic storage. Codegraph (dependency map + co-change history). Code Index (function/class/test embeddings). Custom guidelines + team learnings stored in vector DB.
- **False positive mitigation:** Generates grep/ast-grep verification scripts before posting comments. Learns from 👍/👎 reactions to filter repo-specific patterns.
- **Scale:** 2M+ repos connected. Most-installed AI app on GitHub. Processes millions of PRs monthly via LanceDB.

**Uber uReview (details above):** 90% of 65,000 weekly diffs reviewed. 75% usefulness. 4-minute median turnaround.

**GitHub Copilot Code Review:** Inline suggestions on PRs, integrated into review workflow. Model: GPT-4.1.

**Sources:** [CodeRabbit on Google Cloud Run](https://cloud.google.com/blog/products/ai-machine-learning/how-coderabbit-built-its-ai-code-review-agent-with-google-cloud-run) | [CodeRabbit large codebase blog](https://www.coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-codebases) | [Faros AI productivity paradox](https://www.faros.ai/blog/ai-software-engineering) | [LogRocket: bottleneck shift](https://blog.logrocket.com/ai-coding-tools-shift-bottleneck-to-review/)

---

### C. Test Generation and Maintenance

**Companies automating test writing:**
- **Uber AutoCover:** 5,000+ tests/month, LangGraph-based, 2–3× more coverage in half the time vs. industry tools.
- **Devin:** Test coverage improvement from 50–60% to 80–90%.
- **Datadog Bits AI:** Monitors CI logs, auto-iterates on test failures, opens PRs with passing tests.
- **Diffblue:** Java-specific, 250× faster than manual (1 test every 2 seconds). 20× productivity advantage over Copilot+GPT-5. 162 engineer-years saved at one Fortune 500 in 7 months.

**Flaky test automation:**
- **Datadog Bits AI Dev Agent:** Collects historical run information, execution traces, logs; diagnoses root causes; opens production-ready PRs with verified fixes.
- **GitHub Copilot:** Detects and fixes flaky tests via CI integration.
- No company has published a fully autonomous zero-human flaky test remediation system at scale.

**CI cost optimization:**
- Stripe: Selective CI (subset of 3M tests), 2-round maximum, deterministic lint before AI invocation.
- Spotify: Verifiers run only when relevant file types detected, saving unnecessary CI runs.
- CloudBees Smart Tests: Predicts which tests are affected by changes to reduce CI scope.

**Sources:** [Uber AI tools ZenML](https://www.zenml.io/llmops-database/ai-powered-developer-tools-for-code-quality-and-test-generation) | [Datadog Bits AI test optimization](https://www.datadoghq.com/blog/bits-ai-test-optimization/) | [Diffblue benchmark](https://www.diffblue.com/resources/enterprise-test-automation-benchmark-2025/)

---

### D. Codemod / Migration Agents

**Airbnb (detailed case study):**
- **Scale:** 3,500 React test files (Enzyme → React Testing Library) in 6 weeks vs. estimated 1.5 years manual.
- **Architecture:** Step-based state machine. Files move through stages (Enzyme refactor → Jest fix → Lint → TypeScript) only on passing validation. Dynamic retry prompts regenerated per attempt with latest errors.
- **Context injection:** 40,000–100,000 token prompts, pulling 50 related files including sibling tests, migration guidelines, concrete RTL examples.
- **Key finding:** "Selecting correct related files mattered more than prompt engineering." Retry logic with dynamic context beats optimized single-shot prompts.
- **Results:** 97% automated success (vs. 75% static prompting). Some files needed 50–100 retries. "Sample, tune, sweep" approach for long-tail failures.

**Spotify Fleet Management + Honk:**
- Uses existing Fleet Management platform for targeting, PR creation, review routing, merge. Honk only handles the transformation step.
- Standardization cycle: advisory boards decide → Honk drives migrations to 100% → monorepo linting enforces standards → better agent code → easier review → more migrations.

**Stripe:** LLM-assisted migrations via custom Blueprints. Operates on 100M+ lines of Ruby/Sorbet.

**Google:** DIDACT + Gemini for large-scale codemod migrations (details not published in detail).

**AST vs. LLM for codemods:**
- AST-based (jscodeshift, ts-morph): Exact, reliable, but requires manual coding of transformation logic.
- LLM-based: Handles ambiguous transformations, but requires retry loops, validation, and human review. Best for migrations where transformation rules cannot be fully enumerated.
- Hybrid (Shopify Boba): Deterministic AST autocorrect first → LLM handles remaining edge cases. Best of both.

**Sources:** [Airbnb LLM test migration](https://medium.com/airbnb-engineering/accelerating-large-scale-test-migration-with-llms-9565c208023b) | [InfoQ Airbnb](https://www.infoq.com/news/2025/03/airbnb-llm-test-migration/) | [Aviator: code migration with agents](https://www.aviator.co/blog/solving-the-nasty-code-migration-problem-with-assisted-ai-agents/)

---

## THE OPEN-SWE CONVERGENCE

In March 2026, LangChain open-sourced [Open SWE](https://github.com/langchain-ai/open-swe), an MIT-licensed framework that codified the architecture Stripe (Minions), Ramp (Inspect), and Coinbase (Cloudbot) had built independently. The convergence is strong evidence that these patterns are correct:

1. **Isolated cloud sandboxes** with full permissions inside strict boundaries
2. **Slack/Linear as invocation surface** — agents live in developer workflows
3. **Rich startup context** — full issue/thread loaded before agent starts
4. **Curated toolsets** (~15 in Open SWE vs. ~500 in Stripe's Toolshed)
5. **Subagent decomposition** for complex tasks
6. **AGENTS.md** for repo-level guidance
7. **PR-as-unit-of-work** — agent output is always a reviewable PR

**Sources:** [Open SWE LangChain blog](https://blog.langchain.com/open-swe-an-open-source-framework-for-internal-coding-agents/) | [DevOps.com convergence analysis](https://devops.com/open-swe-captures-the-architecture-that-stripe-coinbase-and-ramp-built-independently-for-internal-coding-agents/) | [Open SWE GitHub](https://github.com/langchain-ai/open-swe)

---

## CROSS-COMPANY PATTERN ANALYSIS

### Most Common Isolation Strategy

**Winner: Cloud VM/Container per task** — Modal Sandboxes (Ramp), EC2 devboxes (Stripe), GitHub Actions ephemeral environments (GitHub Copilot), Docker containers (AutoDev, OpenHands), isolated VMs (Devin, Coinbase). Git worktrees are used for lightweight local parallelism (Anthropic internal, community tools like Uzi) but rarely in enterprise production.

**Second:** Pre-warmed image registries to eliminate cold start. Ramp's 30-minute snapshot cycle is the clearest example. Stripe's 10-second devbox spin-up suggests a similar pre-warming approach.

### Most Common Context Strategy

**Winner: Tool-based retrieval (agent fetches what it needs)** — ripgrep, grep, find given as tools. Used by nearly all systems as baseline. Often combined with:
- Static rule files (AGENTS.md, Cursor rules, Stripe's rule files)
- Rich startup context injection from issues/tickets

**Second:** Embedding-based RAG for code completion/review (Cursor, Augment Code, CodeRabbit, Greptile). Less common for background agents; more common for foreground IDE tools.

**Outlier:** Spotify's deliberate choice of static large prompts over RAG — trades token cost for reliability and testability.

### Most Common Feedback Loop Design

**Winner: Lint → test → CI with agent iteration on failures** — Stripe (3-layer validation), Spotify (verifiers as MCP tools), GitHub Copilot (run tests in Actions), Ramp (full-stack services accessible from sandbox). Pattern: deterministic validation tools feed failure output back to agent for up to N iterations.

**Second:** LLM-as-judge (Spotify's veto layer). Less common but growing.

**Unique:** Uber's 5× re-run of uReview on final commits. Datadog's observability-data-driven CI interpretation.

### Most Common Human-in-the-Loop Pattern

**PR review before merge** — universal across Stripe, Ramp, Spotify, GitHub Copilot, LinkedIn, Shopify. Only Coinbase has documented auto-merge capability, and it's for specific validated cases.

**Approval gates for irreversible actions** — LinkedIn, GitHub Copilot explicitly enforce this. Agents can deploy to branches; merging to main requires human approval.

### Patterns Appearing Across Multiple Companies

1. **MCP as universal tool bus:** Stripe (Toolshed), GitHub Copilot, Ramp, LinkedIn, Atlassian, Goose, Uber. MCP is the de facto standard for connecting agents to internal systems.
2. **Slack as first invocation surface:** Stripe, Ramp, Coinbase, Uber — engineers submit tasks where they already work.
3. **Linear/GitHub issues as spec source:** Coinbase, LinkedIn, Open SWE — structured issue context beats free-form prompt.
4. **AGENTS.md / rule files as repo contract:** Stripe, OpenHands, Open SWE, OpenAI Codex, GitHub Copilot.
5. **Deterministic + agent hybrid:** Stripe Blueprints, Shopify Roast, Airbnb state machine, Google KernelEvolve. Pure agent is unreliable; pure determinism can't handle ambiguity.
6. **Background (async) as preferred mode:** Foreground IDE tools for exploration; background agents for tasks with >5 min estimated time.

### Gaps Nobody Has Publicly Solved

1. **Multi-repo dependency graphs at agent runtime:** Agents still struggle with changes that span multiple repositories. No company has published a solved approach.
2. **Agent-to-agent handoff protocols:** Stripe uses subagents, Coinbase uses agent councils, but there's no standard protocol for how agents transfer state, context, and partial work.
3. **Cost governance at scale:** Uber is the only company to publicly acknowledge 6× cost growth. No company has published a solved architecture for token budget management across hundreds of concurrent agents.
4. **Flaky test remediation at scale:** Datadog has a product, but no company has published autonomous end-to-end resolution with measured recall/precision.
5. **Agent evals that predict production quality:** Spotify explicitly said their LLM judge has no evals. The gap between offline benchmark performance and production PR quality is widely noted but not solved.
6. **Long-context reasoning across 10+ file changes:** CCA (Meta/Harvard) shows degradation from 57.8% (1–2 files) to 44.4% (10+ files). This degradation curve is consistent across all published systems.
7. **Feedback capture from code review back to agent:** Most systems treat code review as a terminal step. The annotation/feedback from review is not yet systematically fed back to improve future agent runs at the company level (LinkedIn mentions this as an aspiration).

---

## Sources

**Stripe:** [Minions Part 1](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents) | [Minions Part 2](https://stripe.dev/blog/minions-stripes-one-shot-end-to-end-coding-agents-part-2) | [Sitepoint architecture](https://www.sitepoint.com/stripe-minions-architecture-explained/) | [ByteByteGo](https://blog.bytebytego.com/p/how-stripes-minions-ship-1300-prs)

**Ramp:** [Modal blog](https://modal.com/blog/how-ramp-built-a-full-context-background-coding-agent-on-modal) | [InfoQ](https://www.infoq.com/news/2026/01/ramp-coding-agent-platform/) | [ZenML](https://www.zenml.io/llmops-database/building-an-internal-background-coding-agent-with-full-development-environment-integration)

**Coinbase:** [Enterprise AI agents blog](https://www.coinbase.com/blog/building-enterprise-AI-agents-at-Coinbase) | [NodeSmith](https://www.coinbase.com/blog/NodeSmith-AI-Driven-Automation-for-Blockchain-Node-Upgrades)

**Spotify:** [Honk Part 1](https://engineering.atspotify.com/2025/11/spotifys-background-coding-agent-part-1) | [Honk Part 2](https://engineering.atspotify.com/2025/11/context-engineering-background-coding-agents-part-2) | [Honk Part 3](https://engineering.atspotify.com/2025/12/feedback-loops-background-coding-agents-part-3) | [QCon London 2026](https://www.infoq.com/news/2026/03/spotify-honk-rewrite/)

**Google:** [AI in Software Engineering at Google](https://research.google/blog/ai-in-software-engineering-at-google-progress-and-the-path-ahead/) | [KernelEvolve](https://engineering.fb.com/2026/04/02/developer-tools/kernelevolve-how-metas-ranking-engineer-agent-optimizes-ai-infrastructure/)

**Meta:** [Confucius Code Agent paper](https://arxiv.org/abs/2512.10398) | [MarkTechPost CCA](https://www.marktechpost.com/2026/01/09/meta-and-harvard-researchers-introduce-the-confucius-code-agent-cca-a-software-engineering-agent-that-can-operate-at-large-scale-codebases/) | [DevOps.com CCA](https://devops.com/meta-introduces-confucius-code-agent-a-new-approach-to-ai-powered-software-engineering/)

**LinkedIn:** [QCon AI NY 2025](https://www.infoq.com/news/2025/12/qcon-ai-linkedin/) | [Platform Engineering for AI podcast](https://www.infoq.com/podcasts/platform-engineering-scaling-agents/)

**Shopify:** [Introducing Roast](https://shopify.engineering/introducing-roast) | [Shopify/roast GitHub](https://github.com/Shopify/roast) | [Pragmatic Engineer interview](https://newsletter.pragmaticengineer.com/p/how-ai-is-changing-software-engineering)

**Uber:** [uReview blog](https://www.uber.com/blog/ureview/) | [Pragmatic Engineer Uber deep dive](https://newsletter.pragmaticengineer.com/p/how-uber-uses-ai-for-development) | [AI tools ZenML](https://www.zenml.io/llmops-database/ai-powered-developer-tools-for-code-quality-and-test-generation) | [21,000 hours saved](https://blog.tmcnet.com/blog/rich-tehrani/ai/how-uber-built-ai-agents-that-saved-21000-developer-hours.html)

**Anthropic:** [Effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | [How Anthropic teams use Claude Code](https://www-cdn.anthropic.com/58284b19e702b49db9302d5b6f135ad8871e7658.pdf) | [Coder blog](https://coder.com/blog/inside-anthropics-ai-first-development)

**GitHub Copilot:** [Coding Agent 101](https://github.blog/ai-and-ml/github-copilot/github-copilot-coding-agent-101-getting-started-with-agentic-workflows-on-github/) | [Firewall docs](https://docs.github.com/copilot/customizing-copilot/customizing-or-disabling-the-firewall-for-copilot-coding-agent) | [Agent concepts](https://docs.github.com/en/copilot/concepts/agents/coding-agent/about-coding-agent)

**Microsoft AutoDev:** [ArXiv paper](https://arxiv.org/html/2403.08299v1)

**Atlassian Rovo:** [Rovo Dev CLI](https://www.atlassian.com/blog/announcements/rovo-dev-command-line-interface) | [AI architecture guide](https://www.valiantys.com/en/resources/making-sense-of-atlassians-ai-architecture-a-guide-for-it-leaders-and-builders)

**Block Goose:** [Block announcement](https://block.xyz/inside/block-open-source-introduces-codename-goose) | [GitHub repo](https://github.com/block/goose) | [Linux Foundation](https://www.linuxfoundation.org/press/linux-foundation-announces-the-formation-of-the-agentic-ai-foundation)

**Cursor:** [Codebase indexing](https://docs.cursor.com/context/codebase-indexing) | [How Cursor indexes](https://towardsdatascience.com/how-cursor-actually-indexes-your-codebase/) | [Secure indexing](https://cursor.com/blog/secure-codebase-indexing) | [ByteByteGo](https://blog.bytebytego.com/p/how-cursor-serves-billions-of-ai)

**Devin:** [Annual performance review 2025](https://cognition.ai/blog/devin-annual-performance-review-2025) | [Devin 2.0 architecture](https://medium.com/@takafumi.endo/agent-native-development-a-deep-dive-into-devin-2-0s-technical-design-3451587d23c0)

**OpenHands:** [SDK paper](https://arxiv.org/html/2511.03690v1) | [Platform paper ICLR 2025](https://arxiv.org/abs/2407.16741)

**Open SWE / Convergence:** [LangChain blog](https://blog.langchain.com/open-swe-an-open-source-framework-for-internal-coding-agents/) | [DevOps.com analysis](https://devops.com/open-swe-captures-the-architecture-that-stripe-coinbase-and-ramp-built-independently-for-internal-coding-agents/) | [GitHub](https://github.com/langchain-ai/open-swe)

**CodeRabbit:** [Google Cloud Run architecture](https://cloud.google.com/blog/products/ai-machine-learning/how-coderabbit-built-its-ai-code-review-agent-with-google-cloud-run) | [Large codebase blog](https://www.coderabbit.ai/blog/how-coderabbit-delivers-accurate-ai-code-reviews-on-massive-codebases)

**Greptile:** [Graph-based context docs](https://www.greptile.com/docs/how-greptile-works/graph-based-codebase-context) | [HN Launch](https://news.ycombinator.com/item?id=39604961)

**Sourcegraph/Cody:** [How Cody understands codebases](https://sourcegraph.com/blog/how-cody-understands-your-codebase)

**Augment Code:** [Real-time index blog](https://www.augmentcode.com/blog/a-real-time-index-for-your-codebase-secure-personal-scalable)

**Airbnb:** [LLM test migration blog](https://medium.com/airbnb-engineering/accelerating-large-scale-test-migration-with-llms-9565c208023b) | [InfoQ](https://www.infoq.com/news/2025/03/airbnb-llm-test-migration/)

**Diffblue:** [Benchmark 2025](https://www.diffblue.com/resources/enterprise-test-automation-benchmark-2025/)

**Review bottleneck research:** [Faros AI productivity paradox](https://www.faros.ai/blog/ai-software-engineering) | [LogRocket](https://blog.logrocket.com/ai-coding-tools-shift-bottleneck-to-review/)

**AGENTS.md:** [agents.md site](https://agents.md/) | [GitHub blog: how to write AGENTS.md](https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/)

**Academic papers:** [Codebase-Memory (Tree-Sitter + MCP)](https://arxiv.org/html/2603.27277) | [Confucius Code Agent](https://arxiv.org/abs/2512.10398) | [OpenHands SDK](https://arxiv.org/abs/2511.03690) | [RAG for code survey](https://arxiv.org/html/2510.04905v1)