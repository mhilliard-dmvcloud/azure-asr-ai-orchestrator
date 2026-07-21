from models.asr_request import ASRRequest
from models.execution_plan import ExecutionPlan
from models.execution_step import ExecutionStep


class ExecutionPlanBuilder:
    """Builds a read-only Azure Site Recovery precheck plan."""

    def build_precheck_plan(
        self,
        request: ASRRequest,
    ) -> ExecutionPlan:
        steps: list[ExecutionStep] = []

        # Step 1: Source resource group
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
                    ),
                },
            )
        )

        # Step 2: Cache storage account
        if (
            request.cache_storage_account
            and request.cache_storage_resource_group
        ):
            steps.append(
                ExecutionStep(
                    step_id="check-cache-storage-account",
                    name="Check cache storage account",
                    description=(
                        "Verify that the Azure Site Recovery cache "
                        "storage account exists in the source region "
                        "and has supported storage properties."
                    ),
                    tool_name="check_cache_storage_account",
                    parameters={
                        "resource_group_name": (
                            request.cache_storage_resource_group
                        ),
                        "storage_account_name": (
                            request.cache_storage_account
                        ),
                        "expected_location": (
                            request.source_region
                        ),
                    },
                )
            )

        # Step 3: Target resource group
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
                        ),
                    },
                )
            )

        # Step 4: Target virtual network
        if (
            request.target_resource_group
            and request.target_vnet
        ):
            steps.append(
                ExecutionStep(
                    step_id="check-target-virtual-network",
                    name="Check target virtual network",
                    description=(
                        "Verify that the target virtual network "
                        "exists in the target region and is ready "
                        "for Site Recovery failover."
                    ),
                    tool_name="check_target_virtual_network",
                    parameters={
                        "resource_group_name": (
                            request.target_resource_group
                        ),
                        "virtual_network_name": (
                            request.target_vnet
                        ),
                        "expected_location": (
                            request.target_region
                        ),
                    },
                )
            )

        # Step 5: Target subnet
        if (
            request.target_resource_group
            and request.target_vnet
            and request.target_subnet
        ):
            steps.append(
                ExecutionStep(
                    step_id="check-target-subnet",
                    name="Check target subnet",
                    description=(
                        "Verify that the target subnet exists and "
                        "return its address space, NSG, route table, "
                        "and network policy configuration."
                    ),
                    tool_name="check_target_subnet",
                    parameters={
                        "resource_group_name": (
                            request.target_resource_group
                        ),
                        "virtual_network_name": (
                            request.target_vnet
                        ),
                        "subnet_name": (
                            request.target_subnet
                        ),
                    },
                )
            )

        # Step 6: Recovery Services vault
        if (
            request.vault_name
            and request.vault_resource_group
        ):
            steps.append(
                ExecutionStep(
                    step_id="check-recovery-services-vault",
                    name="Check Recovery Services vault",
                    description=(
                        "Verify that the Recovery Services vault "
                        "exists and matches the expected location."
                    ),
                    tool_name="check_recovery_services_vault",
                    parameters={
                        "resource_group_name": (
                            request.vault_resource_group
                        ),
                        "vault_name": (
                            request.vault_name
                        ),
                        "expected_location": (
                            request.target_region
                        ),
                    },
                )
            )

        return ExecutionPlan(
            name="Azure Site Recovery Precheck Plan",
            description=(
                f"Read-only prechecks for VM "
                f"'{request.vm_name}' from "
                f"'{request.source_region}' to "
                f"'{request.target_region}'."
            ),
            steps=steps,
        )