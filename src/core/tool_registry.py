from core.base_tool import BaseTool
from models.tool_result import ToolResult


class ToolRegistry:
    """Stores and executes tools available to the orchestrator."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ValueError(
                f"A tool named '{tool.name}' is already registered."
            )

        self._tools[tool.name] = tool

    def get(self, tool_name: str) -> BaseTool:
        tool = self._tools.get(tool_name)

        if tool is None:
            raise KeyError(
                f"Tool '{tool_name}' is not registered."
            )

        return tool

    def list_tools(self) -> list[dict[str, str]]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
            }
            for tool in self._tools.values()
        ]

    def execute(self, tool_name: str, **kwargs) -> ToolResult:
        tool = self.get(tool_name)

        return tool.execute(**kwargs)