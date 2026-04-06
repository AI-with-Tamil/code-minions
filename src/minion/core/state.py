"""RunState — minimal default state when no state_cls is provided."""

from __future__ import annotations

from pydantic import BaseModel


class RunState(BaseModel):
    """Minimal state used when Blueprint has no explicit state_cls."""
    outcome: str = "pending"
