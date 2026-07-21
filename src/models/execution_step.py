from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ExecutionStep:
    """Represents one step in an ASR execution plan."""

    step_id: str
    name: str
    description: str
    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    requires_approval: bool = False
    status: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)