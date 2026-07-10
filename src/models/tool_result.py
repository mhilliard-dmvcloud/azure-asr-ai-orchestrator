from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """Standard result returned by every orchestrator tool."""

    tool_name: str
    status: str
    message: str
    severity: str = "info"
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert the result into a regular dictionary."""
        return asdict(self)