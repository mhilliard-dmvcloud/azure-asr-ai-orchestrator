from dataclasses import asdict, dataclass, field
from typing import Any

from models.execution_step import ExecutionStep


@dataclass
class ExecutionPlan:
    """Contains the ordered steps for an ASR workflow."""

    name: str
    description: str
    steps: list[ExecutionStep] = field(default_factory=list)
    status: str = "pending"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)