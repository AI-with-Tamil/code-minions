"""Built-in progress tools: write_todos, get_todos."""

from __future__ import annotations

from minion.core.context import RunContext
from minion.core.tool import tool


@tool(description="Create or update a structured task list for tracking work")
async def write_todos(
    ctx: RunContext,
    todos: list[dict],
) -> str:
    """Write a structured todo list to track progress within a task.

    Each todo is a dict with: {"id": "1", "description": "...", "status": "pending"}
    Status values: pending, in_progress, completed, skipped

    The list is stored on ctx.state._todos (not persisted to disk).
    Helps the agent organize multi-step work and stay on track.
    """
    # Validate each todo
    valid = []
    for t in todos:
        if not isinstance(t, dict):
            continue
        todo = {
            "id": str(t.get("id", len(valid) + 1)),
            "description": str(t.get("description", "")),
            "status": str(t.get("status", "pending")),
        }
        if todo["status"] not in ("pending", "in_progress", "completed", "skipped"):
            todo["status"] = "pending"
        valid.append(todo)

    # Store on state
    if not hasattr(ctx.state, "_todos"):
        object.__setattr__(ctx.state, "_todos", [])
    object.__setattr__(ctx.state, "_todos", valid)

    # Format summary
    counts = {"pending": 0, "in_progress": 0, "completed": 0, "skipped": 0}
    for t in valid:
        counts[t["status"]] = counts.get(t["status"], 0) + 1

    return (
        f"Todos updated: {len(valid)} items "
        f"({counts['completed']} done, {counts['in_progress']} active, "
        f"{counts['pending']} pending, {counts['skipped']} skipped)"
    )


@tool(description="Get the current task list")
async def get_todos(ctx: RunContext) -> str:
    """Return the current todo list as formatted text."""
    todos = getattr(ctx.state, "_todos", [])
    if not todos:
        return "(no todos set — use write_todos to create a task list)"

    lines = []
    status_icons = {
        "completed": "[x]",
        "in_progress": "[>]",
        "pending": "[ ]",
        "skipped": "[-]",
    }
    for t in todos:
        icon = status_icons.get(t["status"], "[ ]")
        lines.append(f"  {icon} {t['id']}: {t['description']}")

    counts = {}
    for t in todos:
        counts[t["status"]] = counts.get(t["status"], 0) + 1
    summary = ", ".join(f"{v} {k}" for k, v in counts.items() if v > 0)

    return f"Todos ({summary}):\n" + "\n".join(lines)
