from models.asr_request import ASRRequest
from models.execution_plan import ExecutionPlan
from models.execution_step import ExecutionStep


class ExecutionPlanBuilder:
    """Builds a read-only ASR precheck plan."""

    def build_precheck_plan(
        self,
        request: ASRRequest,
    ) -> ExecutionPlan:
        steps: list[ExecutionStep] = []

        steps.append(
            ExecutionStep(
                step_id="check-source-resource-group",
                name="Check source resource group",
                description=(
                    "Verify that the source VM resource group exists."
                ),
                tool_name="check_resource_group",
                parameters={
                    "resource_group_name": (
                        request.source_resource_group
                    )
                },
            )
        )

        if request.target_resource_group:
            steps.append(
                ExecutionStep(
                    step_id="check-target-resource-group",
                    name="Check target resource group",
                    description=(
                        "Verify that the target resource group exists."
                    ),
                    tool_name="check_resource_group",
                    parameters={
                        "resource_group_name": (
                            request.target_resource_group
                        )
                    },
                )
            )

        if request.vault_name and request.vault_resource_group:
            steps.append(
                ExecutionStep(
                    step_id="check-recovery-services-vault",
                    name="Check Recovery Services vault",
                    description=(
                        "Verify that the Recovery Services vault exists "
                        "and matches the expected location."
                    ),
                    tool_name="check_recovery_services_vault",
                    parameters={
                        "resource_group_name": (
                            request.vault_resource_group
                        ),
                        "vault_name": request.vault_name,
                        "expected_location": request.target_region,
                    },
                )
            )

        return ExecutionPlan(
            name="Azure Site Recovery Precheck Plan",
            description=(
                f"Read-only prechecks for VM '{request.vm_name}' "
                f"from '{request.source_region}' to "
                f"'{request.target_region}'."
            ),
            steps=steps,
        )