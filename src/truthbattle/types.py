from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

TaskType = Literal[
    "solve",
    "simplify",
    "differentiate",
    "integrate",
    "ode",
    "explain",
]
NodeStatus = Literal[
    "ok",
    "pass",
    "partial",
    "fail",
    "skipped",
    "unsupported",
    "error",
]


@dataclass
class TaskSpec:
    task_type: TaskType
    expression: str = ""
    lhs: str = ""
    rhs: str = ""
    variable: str = "x"
    domain: str = "unspecified"
    assumptions: list[str] | None = None
    reasoning: str = ""


@dataclass
class NodeTrace:
    node: str
    status: NodeStatus
    summary: str
    payload: dict[str, Any] | None = None


@dataclass
class TutorResult:
    task: TaskSpec
    lean_first: dict[str, Any]
    sympy: dict[str, Any]
    verification: dict[str, Any]
    graph: dict[str, Any]
    verdict: dict[str, Any]
    trace: list[NodeTrace]
    final_answer: str
    raw_question: str
