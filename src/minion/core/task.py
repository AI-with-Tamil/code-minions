"""Task — structured input to a Minion run."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class Task(BaseModel):
    """Structured input to a Minion run.

    Not just a string — carries context, acceptance criteria, constraints,
    and arbitrary metadata from the caller.
    """

    model_config = {"frozen": True}

    description: str
    context: list[str] = Field(default_factory=list)
    acceptance: str = ""
    constraints: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _coerce_string(cls, data: Any) -> Any:
        if isinstance(data, str):
            return {"description": data}
        return data

    # Convenience properties for prompt template rendering
    @property
    def context_list(self) -> str:
        """Newline-joined context items for prompt templates."""
        return "\n".join(f"- {c}" for c in self.context) if self.context else "(none)"

    @property
    def constraints_list(self) -> str:
        """Newline-joined constraints for prompt templates."""
        return "\n".join(f"- {c}" for c in self.constraints) if self.constraints else "(none)"


def coerce_task(task: str | Task) -> Task:
    """Convert a string or Task to a Task. Used internally by Minion."""
    if isinstance(task, Task):
        return task
    return Task(description=task)
