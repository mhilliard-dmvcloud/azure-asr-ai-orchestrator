from collections.abc import Callable

from core.tool_registry import ToolRegistry
from models.execution_plan import ExecutionPlan
from models.execution_step import ExecutionStep


ProgressCallback = Callable[[ExecutionStep], None]


class ExecutionEngine:
    """Executes an ordered plan through the Tool Registry."""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    def execute_plan(
        self,
        plan: ExecutionPlan,
        progress_callback: ProgressCallback | None = None,
    ) -> ExecutionPlan:
        plan.status = "running"

        for step in plan.steps:
            step.status = "running"

            if progress_callback:
                progress_callback(step)

            try:
                tool_result = self.registry.execute(
                    step.tool_name,
                    **step.parameters,
                )

                step.result = tool_result.to_dict()

                if tool_result.status == "success":
                    step.status = "completed"
                elif tool_result.status in {
                    "not_found",
                    "validation_failed",
                }:
                    step.status = "warning"
                else:
                    step.status = "failed"

            except Exception as error:
                step.status = "failed"
                step.error = str(error)

            if progress_callback:
                progress_callback(step)

        if any(step.status == "failed" for step in plan.steps):
            plan.status = "failed"
        elif any(step.status == "warning" for step in plan.steps):
            plan.status = "completed_with_warnings"
        else:
            plan.status = "completed"

        return plan