"""RunResult / EscalationResult — output of a Minion run."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pprint import pprint
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from codeminions.trace import Trace


@dataclass
class RunResult:
    run_id: str
    outcome: Literal["passed", "failed", "escalated"]
    branch: str | None
    diff: str
    summary: str
    state: BaseModel
    trace: "Trace"
    tokens: int
    duration_ms: int
    working_dir: str | None = field(default=None, repr=False, compare=False)

    # --- Actions ---

    def open_pr(self) -> str:
        if not self.working_dir:
            raise RuntimeError("RunResult has no working directory for PR creation")
        title = f"minion: {self.summary or self.run_id}"
        body = self.summary or f"Automated by CodeMinions\n\nRun: {self.run_id}"
        proc = subprocess.run(
            ["gh", "pr", "create", "--title", title, "--body", body],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "gh pr create failed")
        return proc.stdout.strip()

    def push(self) -> None:
        if not self.working_dir:
            raise RuntimeError("RunResult has no working directory for push")
        if not self.branch:
            raise RuntimeError("RunResult has no branch to push")
        proc = subprocess.run(
            ["git", "push", "-u", "origin", self.branch],
            cwd=self.working_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or "git push failed")

    def inspect(self) -> None:
        pprint(self.trace.events)

    # --- Test assertions ---

    def assert_passed(self) -> None:
        assert self.outcome == "passed", f"Expected passed, got {self.outcome}"

    def assert_failed(self) -> None:
        assert self.outcome == "failed", f"Expected failed, got {self.outcome}"

    def assert_escalated(self) -> None:
        assert self.outcome == "escalated", f"Expected escalated, got {self.outcome}"

    def assert_outcome(self, outcome: Literal["passed", "failed", "escalated"]) -> None:
        assert self.outcome == outcome, f"Expected {outcome}, got {self.outcome}"

    def assert_node_ran(self, name: str) -> None:
        ran = {e.node for e in self.trace.events if e.type == "node_start"}
        assert name in ran, f"Node '{name}' did not run. Ran: {ran}"

    def assert_node_skipped(self, name: str) -> None:
        skipped = {e.node for e in self.trace.events if e.type == "node_skip"}
        assert name in skipped, f"Node '{name}' was not skipped. Skipped: {skipped}"

    def assert_nodes_ran_in_order(self, *names: str) -> None:
        ran_order = [e.node for e in self.trace.events if e.type == "node_start"]
        filtered = [n for n in ran_order if n in names]
        assert filtered == list(names), (
            f"Expected order {list(names)}, got {filtered}"
        )

    def assert_tool_called(self, name: str, **kwargs: object) -> None:
        for e in self.trace.events:
            if e.type == "tool_call" and e.data.get("tool") == name:
                if kwargs:
                    args = e.data.get("args", {})
                    for k, v in kwargs.items():
                        if args.get(k) != v:
                            break
                    else:
                        return
                else:
                    return
        assert False, f"Tool '{name}' was not called with {kwargs}" if kwargs else f"Tool '{name}' was not called"

    def assert_tool_not_called(self, name: str) -> None:
        for e in self.trace.events:
            if e.type == "tool_call" and e.data.get("tool") == name:
                assert False, f"Tool '{name}' was called but should not have been"

    def assert_tokens_under(self, limit: int) -> None:
        assert self.tokens <= limit, f"Token usage {self.tokens} exceeds limit {limit}"

    def assert_duration_under(self, ms: int) -> None:
        assert self.duration_ms <= ms, f"Duration {self.duration_ms}ms exceeds limit {ms}ms"

    def assert_judge_approved(self, node: str) -> None:
        """Assert that JudgeNode *node* produced a final APPROVE verdict."""
        for e in self.trace.events:
            if e.type == "judge_approve" and e.node == node:
                return
        node_events = [e.type for e in self.trace.events if e.node == node]
        assert False, f"JudgeNode '{node}' did not approve. Node events: {node_events}"

    def assert_judge_vetoed(self, node: str, reason: str | None = None) -> None:
        """Assert that JudgeNode *node* issued at least one veto.

        If *reason* is given, it must appear (case-insensitive) in the veto reason.
        """
        for e in self.trace.events:
            if e.type == "judge_veto" and e.node == node:
                if reason is None:
                    return
                if reason.lower() in e.data.get("reason", "").lower():
                    return
        msg = f"JudgeNode '{node}' did not veto"
        if reason:
            msg += f" with reason containing '{reason}'"
        assert False, msg

    def judge_verdicts(self) -> dict[str, str]:
        """Return the final verdict for each judge node that ran.

        Returns ``{node_name: "approved" | "vetoed: <reason>"}`` keyed by
        judge node name. When a node vetoed then retried and approved, the
        last event wins — so the returned value is "approved".
        """
        verdicts: dict[str, str] = {}
        for e in self.trace.events:
            if e.type == "judge_approve":
                verdicts[e.node] = "approved"
            elif e.type == "judge_veto":
                verdicts[e.node] = f"vetoed: {e.data.get('reason', '')}"
        return verdicts


@dataclass
class EscalationResult(RunResult):
    node: str = ""
    reason: str = ""
    last_failure: str = ""

    def __post_init__(self) -> None:
        self.outcome = "escalated"
