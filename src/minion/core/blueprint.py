"""Blueprint — ordered list of nodes defining the full lifecycle of a task."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from minion.core.node import (
    AgentNode,
    AnyNode,
    DeterministicNode,
    JudgeNode,
    LoopNode,
    ParallelNode,
)


class BlueprintValidationError(Exception):
    """Raised when blueprint validation fails. Contains actionable messages."""


@dataclass
class Blueprint:
    """An ordered list of nodes — NOT a graph.

    Sequence with conditional skipping. 95% of real workflows are sequential
    with conditional steps.
    """
    name: str
    nodes: list[AnyNode] = field(default_factory=list)
    state_cls: type[BaseModel] | None = None

    # --- Validation ---

    def validate(self) -> None:
        """Validate the blueprint. Raises BlueprintValidationError with actionable messages."""
        issues: list[str] = []

        # Check node names unique
        names: dict[str, int] = {}
        for i, node in enumerate(self.nodes):
            if node.name in names:
                issues.append(
                    f"Node '{node.name}' (index {i}): duplicate name, "
                    f"first seen at index {names[node.name]}"
                )
            names[node.name] = i

        # Collect all node names including nested
        all_names = self._collect_node_names()

        # Check JudgeNode.evaluates references
        for i, node in enumerate(self.nodes):
            if isinstance(node, JudgeNode):
                if node.evaluates not in all_names:
                    issues.append(
                        f"Node '{node.name}' (index {i}): JudgeNode.evaluates='{node.evaluates}' "
                        f"but no AgentNode named '{node.evaluates}' exists in this blueprint"
                    )
            elif isinstance(node, ParallelNode):
                for child in node.nodes:
                    if isinstance(child, JudgeNode) and child.evaluates not in all_names:
                        issues.append(
                            f"Node '{child.name}' (in ParallelNode '{node.name}'): "
                            f"JudgeNode.evaluates='{child.evaluates}' "
                            f"but no AgentNode named '{child.evaluates}' exists"
                        )

        # Check state_cls has defaults on all fields
        if self.state_cls is not None:
            for fname, finfo in self.state_cls.model_fields.items():
                if finfo.is_required():
                    issues.append(
                        f"state_cls '{self.state_cls.__name__}': field '{fname}' has no default. "
                        f"All state fields must have defaults."
                    )

        # Check AgentNode max_rounds
        for i, node in enumerate(self.nodes):
            if isinstance(node, AgentNode) and node.max_rounds < 1:
                issues.append(
                    f"Node '{node.name}' (index {i}): max_rounds must be >= 1, got {node.max_rounds}"
                )

        # Check LoopNode sub_blueprint
        for i, node in enumerate(self.nodes):
            if isinstance(node, LoopNode):
                if not isinstance(node.sub_blueprint, Blueprint):
                    issues.append(
                        f"Node '{node.name}' (index {i}): sub_blueprint must be a Blueprint instance"
                    )

        if issues:
            issue_text = "\n".join(f"  {j+1}. {msg}" for j, msg in enumerate(issues))
            raise BlueprintValidationError(
                f"{len(issues)} issue(s) in blueprint '{self.name}':\n\n{issue_text}"
            )

    def _collect_node_names(self) -> set[str]:
        """Collect all node names including nested ones."""
        names: set[str] = set()
        for node in self.nodes:
            names.add(node.name)
            if isinstance(node, ParallelNode):
                for child in node.nodes:
                    names.add(child.name)
            elif isinstance(node, LoopNode) and isinstance(node.sub_blueprint, Blueprint):
                for child in node.sub_blueprint.nodes:
                    names.add(child.name)
        return names

    # --- Composition ---

    def __add__(self, other: Blueprint) -> Blueprint:
        """Concatenate two blueprints."""
        return Blueprint(
            name=f"{self.name}+{other.name}",
            nodes=[*self.nodes, *other.nodes],
            state_cls=self.state_cls or other.state_cls,
        )

    def before(self, name: str, node: AnyNode) -> Blueprint:
        """Insert a node before the named node. Returns a new Blueprint."""
        new_nodes: list[AnyNode] = []
        found = False
        for existing in self.nodes:
            if existing.name == name:
                new_nodes.append(node)
                found = True
            new_nodes.append(existing)
        if not found:
            raise ValueError(f"No node named '{name}' in blueprint '{self.name}'")
        return Blueprint(name=self.name, nodes=new_nodes, state_cls=self.state_cls)

    def after(self, name: str, node: AnyNode) -> Blueprint:
        """Insert a node after the named node. Returns a new Blueprint."""
        new_nodes: list[AnyNode] = []
        found = False
        for existing in self.nodes:
            new_nodes.append(existing)
            if existing.name == name:
                new_nodes.append(node)
                found = True
        if not found:
            raise ValueError(f"No node named '{name}' in blueprint '{self.name}'")
        return Blueprint(name=self.name, nodes=new_nodes, state_cls=self.state_cls)

    def replace(self, name: str, node: AnyNode) -> Blueprint:
        """Replace a node by name. Returns a new Blueprint."""
        new_nodes: list[AnyNode] = []
        found = False
        for existing in self.nodes:
            if existing.name == name:
                new_nodes.append(node)
                found = True
            else:
                new_nodes.append(existing)
        if not found:
            raise ValueError(f"No node named '{name}' in blueprint '{self.name}'")
        return Blueprint(name=self.name, nodes=new_nodes, state_cls=self.state_cls)

    def without(self, name: str) -> Blueprint:
        """Remove a node by name. Returns a new Blueprint."""
        new_nodes = [n for n in self.nodes if n.name != name]
        if len(new_nodes) == len(self.nodes):
            raise ValueError(f"No node named '{name}' in blueprint '{self.name}'")
        return Blueprint(name=self.name, nodes=new_nodes, state_cls=self.state_cls)
