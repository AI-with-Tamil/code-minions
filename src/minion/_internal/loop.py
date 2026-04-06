"""AgentLoop — the internal tool-calling loop for AgentNode execution."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any

from minion.core.context import RunContext
from minion.core.tool import Tool, ToolResult
from minion.models._base import Message, ModelResponse, ToolCall, ToolSchema


class _AgentDone(BaseException):
    """Raised when the agent calls done(). Not an error — clean exit signal.

    Inherits from BaseException (not Exception) so it escapes Tool.execute()'s
    generic except Exception handler.
    """
    def __init__(self, summary: str, files_changed: list[str]) -> None:
        self.summary = summary
        self.files_changed = files_changed


@dataclass
class AgentLoopResult:
    summary: str
    files_changed: list[str]
    total_input_tokens: int
    total_output_tokens: int
    iterations: int
    exhausted: bool       # True if budget/iterations ran out without done()


def _build_done_tool() -> Tool:
    """Build the auto-injected done() tool."""
    from minion.core.tool import Tool, ToolOutputPolicy

    async def done_fn(ctx: RunContext, summary: str, files_changed: list[str] = []) -> str:  # noqa: B006
        raise _AgentDone(summary=summary, files_changed=files_changed)

    return Tool(
        name="done",
        description="Call this when you have completed the task. Provide a summary and list of changed files.",
        fn=done_fn,
        parameters={
            "summary": {"type": "string"},
            "files_changed": {"type": "array", "items": {"type": "string"}, "default": []},
        },
        required=["summary"],
        output_policy=ToolOutputPolicy(),
        is_async=True,
    )


def _render_prompt(template: str, ctx: RunContext) -> str:
    """Render a system prompt template against ctx.

    Supports {task.description}, {task.acceptance}, {task.constraints_list},
    {task.context_list}, {state.branch}, {state.current_feature}, etc.
    """
    # Build a namespace for format
    ns: dict[str, Any] = {}

    # Task attributes
    task = ctx.task
    ns["task"] = task

    # State attributes — expose as an object with attribute access
    ns["state"] = ctx.state

    # Use format_map with a fallback dict
    class _Namespace:
        def __init__(self, data: dict[str, Any]) -> None:
            self._data = data
        def __getitem__(self, key: str) -> Any:
            return self._data[key]
        def __contains__(self, key: str) -> bool:
            return key in self._data

    try:
        return template.format_map(ns)
    except (KeyError, AttributeError, IndexError):
        return template


async def run_agent_loop(
    ctx: RunContext,
    system_prompt: str,
    tools: list[Tool],
    max_iterations: int,
    token_budget: int,
    veto_reason: str | None = None,
) -> AgentLoopResult:
    """Run the agent loop for an AgentNode.

    Returns AgentLoopResult. If the agent calls done(), summary is from done().
    If budget exhausted, exhausted=True.
    """
    # Inject done() tool
    done_tool = _build_done_tool()
    all_tools = [*tools, done_tool]

    # Build tool schemas
    tool_schemas = [
        ToolSchema(
            name=t.name,
            description=t.description,
            input_schema={
                "type": "object",
                "properties": t.parameters,
                "required": t.required,
            },
        )
        for t in all_tools
    ]

    # Build tool lookup
    tool_map = {t.name: t for t in all_tools}

    # Render system prompt
    rendered_prompt = _render_prompt(system_prompt, ctx)
    if veto_reason:
        rendered_prompt += (
            f"\n\n--- PREVIOUS ATTEMPT VETOED ---\n"
            f"Reason: {veto_reason}\n"
            f"Fix the issues identified above and try again."
        )

    # Build initial user message from task
    user_content = f"Task: {ctx.task.description}"
    if ctx.task.acceptance:
        user_content += f"\n\nAcceptance criteria: {ctx.task.acceptance}"
    if ctx.task.constraints:
        user_content += f"\n\nConstraints:\n" + "\n".join(f"- {c}" for c in ctx.task.constraints)
    if ctx.task.context:
        user_content += f"\n\nContext files:\n" + "\n".join(f"- {c}" for c in ctx.task.context)

    messages: list[Message] = [Message(role="user", content=user_content)]

    total_input = 0
    total_output = 0
    iterations = 0

    for _ in range(max_iterations):
        # Check token budget
        if total_input + total_output >= token_budget:
            break

        # Call model
        response: ModelResponse = await ctx.model.call(
            messages=messages,
            tools=tool_schemas,
            system=rendered_prompt,
            max_tokens=min(4096, token_budget - total_input - total_output),
        )

        total_input += response.input_tokens
        total_output += response.output_tokens
        iterations += 1
        ctx.trace.record(
            "model_response",
            ctx.node,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            stop_reason=response.stop_reason,
            iteration=iterations,
        )

        # No tool calls — agent is done talking
        if not response.tool_calls:
            if response.text:
                messages.append(Message(role="assistant", content=response.text))
            break

        # Record assistant message with tool calls
        messages.append(Message(
            role="assistant",
            content=response.text,
            tool_calls=response.tool_calls,
        ))

        # Execute each tool call
        for tc in response.tool_calls:
            ctx.trace.record_tool_call(ctx.node, tc.name, tc.args)

            tool_obj = tool_map.get(tc.name)
            if tool_obj is None:
                result = ToolResult(error=f"Unknown tool: {tc.name}")
            else:
                try:
                    result = await tool_obj.execute(ctx, **tc.args)
                except _AgentDone as done:
                    ctx.trace.record("agent_done", ctx.node,
                                     summary=done.summary,
                                     files_changed=done.files_changed)
                    return AgentLoopResult(
                        summary=done.summary,
                        files_changed=done.files_changed,
                        total_input_tokens=total_input,
                        total_output_tokens=total_output,
                        iterations=iterations,
                        exhausted=False,
                    )

            ctx.trace.record_tool_result(
                ctx.node, tc.name,
                result=result.content,
                error=result.error,
            )

            # Add tool result message
            content = result.content or result.error or ""
            messages.append(Message(
                role="tool",
                content=content,
                tool_call_id=tc.id or uuid.uuid4().hex[:8],
            ))

    # Exhausted without done()
    return AgentLoopResult(
        summary="Agent did not call done()",
        files_changed=[],
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        iterations=iterations,
        exhausted=True,
    )
