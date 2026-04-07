"""
Example 05 — Anthropic Two-Agent Pattern
==========================================
Initializer sets up context. Coder picks up and executes. Clean session handoff.
Inspired by Anthropic's internal usage: engineers run 5-10 Claude instances simultaneously.

Example type:
- Research example
- Pressure test of explicit session handoff through a progress artifact
- Approximation of Anthropic-style multi-session coding workflows

Pattern:
    initializer → load_progress → coder → save_progress

What is directly modeled:
- Feature list in JSON, not Markdown (JSON resists unintended model modification)
- One feature per session to prevent context exhaustion
- Initializer creates a progress artifact that later sessions can resume from
- Coder reads progress + git history each session, picks next task, commits, ends clean
- Progress file is the handoff protocol between sessions

What is approximated:
- the broader "many parallel sessions" operating style is collapsed here into a single blueprint run
- init scripts, browser automation, and richer environment setup are represented through the progress file and deterministic setup steps rather than external tooling

What this example proves:
- Two sequential AgentNodes with explicit state handoff via a progress file
- DeterministicNode reads the progress file to drive coder's context
- The "initializer" pattern: setup once, execute N times cleanly
- Progress-file handoff is an explicit contract, not hidden prompt state
"""

import json
from pydantic import BaseModel

from codeminions import (
    AgentNode,
    Blueprint,
    DeterministicNode,
    Minion,
    RunContext,
)
from codeminions.tools import CODE_TOOLS, SHELL_TOOLS

PROGRESS_FILE = "claude-progress.json"


class TwoAgentState(BaseModel):
    branch: str = ""
    features: list[dict] = []          # [{id, description, status}]
    current_feature: dict = {}
    completed: list[str] = []
    failed: list[str] = []


# --- Setup phase ---

async def create_branch(ctx: RunContext) -> None:
    ctx.state.branch = f"codeminions/{ctx.run_id[:8]}"
    await ctx.exec(f"git checkout -b {ctx.state.branch}")


async def load_progress(ctx: RunContext) -> None:
    """Load the progress file written by the initializer."""
    content = await ctx.read(PROGRESS_FILE)
    data = json.loads(content)
    ctx.state.features = data["features"]
    ctx.state.completed = data.get("completed", [])

    # Find next pending feature
    pending = [f for f in ctx.state.features if f["status"] == "pending"]
    if pending:
        ctx.state.current_feature = pending[0]
        ctx.log(f"Next feature: {ctx.state.current_feature['description']}")
    else:
        ctx.log("All features complete")


async def save_progress(ctx: RunContext) -> None:
    """Update progress file after coder completes."""
    progress = {
        "features": ctx.state.features,
        "completed": ctx.state.completed,
        "failed": ctx.state.failed,
    }
    for f in progress["features"]:
        if f["id"] in ctx.state.completed:
            f["status"] = "done"
        elif f["id"] in ctx.state.failed:
            f["status"] = "failed"

    await ctx.write(PROGRESS_FILE, json.dumps(progress, indent=2))
    await ctx.exec("git add -A")
    await ctx.exec(f"git commit -m \"minion: complete feature {ctx.state.current_feature.get('id', '')}\"")


# --- Blueprint ---

two_agent_blueprint = Blueprint(
    name="anthropic_two_agent",
    state_cls=TwoAgentState,
    nodes=[
        DeterministicNode("create_branch", fn=create_branch),

        # Initializer: reads the task, decomposes into feature list, writes progress file
        AgentNode(
            "initializer",
            system_prompt=(
                "You are setting up a coding session. Your job is to:\n"
                "1. Understand the full task\n"
                "2. Decompose it into a list of independent features\n"
                "3. Write a progress file to disk\n\n"
                f"Write the progress file to `{PROGRESS_FILE}` in this exact JSON format:\n"
                '{"features": [{"id": "f1", "description": "...", "status": "pending"}, ...]}\n\n'
                "Rules:\n"
                "- Use JSON, not Markdown\n"
                "- Each feature must be independently implementable\n"
                "- Maximum 7 features — if more, batch related ones\n"
                "- Be specific: 'Add null check to authenticate()' not 'Fix auth'\n\n"
                "Call done() after writing the progress file."
            ),
            tools=CODE_TOOLS,
            max_iterations=20,
            token_budget=15_000,
        ),

        DeterministicNode("load_progress", fn=load_progress),

        # Coder: reads progress, implements exactly one feature, commits clean
        AgentNode(
            "coder",
            system_prompt=(
                "You are implementing a single feature from a progress file.\n\n"
                "Current feature: {state.current_feature}\n"
                "Progress file: " + PROGRESS_FILE + "\n\n"
                "Rules:\n"
                "- Implement ONLY the current feature — nothing else\n"
                "- Read the progress file and git log first for context\n"
                "- Run tests after implementing\n"
                "- End with a clean working state\n"
                "- Call done() with the feature id in files_changed\n"
            ),
            tools=[*CODE_TOOLS, *SHELL_TOOLS],
            condition=lambda ctx: bool(ctx.state.current_feature),
            max_iterations=60,
            token_budget=50_000,
        ),

        DeterministicNode("save_progress", fn=save_progress),
    ],
)


async def main():
    result = await Minion(
        model="claude-sonnet-4-6",
        blueprint=two_agent_blueprint,
        environment="local",
    ).run(
        "Implement OAuth2 login with Google and GitHub providers, "
        "including token storage, refresh, and revocation"
    )

    print(f"outcome   : {result.outcome}")
    print(f"branch    : {result.branch}")
    print(f"completed : {result.state.completed}")
    print(f"failed    : {result.state.failed}")
    print(f"tokens    : {result.tokens}")


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
