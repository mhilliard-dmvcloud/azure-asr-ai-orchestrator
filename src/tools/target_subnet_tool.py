from core.base_tool import BaseTool
from models.tool_result import ToolResult
from services.azure_resource_service import AzureResourceService


class TargetSubnetTool(BaseTool):
    """Checks the target Azure subnet."""

    API_VERSION = "2025-05-01"

    def __init__(self, azure_service: AzureResourceService):
        super().__init__(
            name="check_target_subnet",
            description=(
                "Checks whether the target subnet exists and returns "
                "its address prefix, NSG, route table, and provisioning state."
            ),
        )
        self.azure_service = azure_service

    def execute(self, **kwargs) -> ToolResult:
        resource_group_name = kwargs.get(
            "resource_group_name",
            "",
        ).strip()

        virtual_network_name = kwargs.get(
            "virtual_network_name",
            "",
        ).strip()

        subnet_name = kwargs.get(
            "subnet_name",
            "",
        ).strip()

        if not resource_group_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Target subnet resource group cannot be empty.",
            )

        if not virtual_network_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Target virtual network name cannot be empty.",
            )

        if not subnet_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Target subnet name cannot be empty.",
            )

        self.log_start()

        path = (
            f"/subscriptions/{self.azure_service.subscription_id}"
            f"/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.Network"
            f"/virtualNetworks/{virtual_network_name}"
            f"/subnets/{subnet_name}"
        )

        result = self.azure_service.get(
            path=path,
            api_version=self.API_VERSION,
        )

        if not result["found"]:
            tool_result = ToolResult(
                tool_name=self.name,
                status="not_found",
                severity="warning",
                message=(
                    f"Target subnet '{subnet_name}' was not found "
                    f"in virtual network '{virtual_network_name}'."
                ),
                data={
                    "subnet_name": subnet_name,
                    "virtual_network_name": virtual_network_name,
                    "resource_group_name": resource_group_name,
                    "exists": False,
                },
            )

            self.log_complete()
            return tool_result

        subnet_data = result.get("data") or {}
        properties = subnet_data.get("properties") or {}

        provisioning_state = properties.get(
            "provisioningState"
        )

        address_prefix = properties.get("addressPrefix")
        address_prefixes = properties.get("addressPrefixes") or []

        effective_prefixes = (
            address_prefixes
            if address_prefixes
            else [address_prefix] if address_prefix else []
        )

        network_security_group = (
            properties.get("networkSecurityGroup") or {}
        )

        route_table = properties.get("routeTable") or {}

        delegations = properties.get("delegations") or []

        private_endpoint_policies = properties.get(
            "privateEndpointNetworkPolicies"
        )

        private_link_service_policies = properties.get(
            "privateLinkServiceNetworkPolicies"
        )

        checks_passed = (
            provisioning_state == "Succeeded"
            and bool(effective_prefixes)
        )

        if checks_passed:
            status = "success"
            severity = "info"
            message = (
                f"Target subnet '{subnet_name}' was found and "
                "passed the core subnet checks."
            )
        else:
            status = "validation_failed"
            severity = "warning"

            failed_checks = []

            if provisioning_state != "Succeeded":
                failed_checks.append(
                    "provisioning state is not Succeeded"
                )

            if not effective_prefixes:
                failed_checks.append(
                    "no subnet address prefix was returned"
                )

            message = (
                f"Target subnet '{subnet_name}' was found, but "
                + "; ".join(failed_checks)
                + "."
            )

        tool_result = ToolResult(
            tool_name=self.name,
            status=status,
            severity=severity,
            message=message,
            data={
                "subnet_name": subnet_name,
                "virtual_network_name": virtual_network_name,
                "resource_group_name": resource_group_name,
                "exists": True,
                "address_prefixes": effective_prefixes,
                "provisioning_state": provisioning_state,
                "network_security_group_id": (
                    network_security_group.get("id")
                ),
                "nsg_attached": bool(
                    network_security_group.get("id")
                ),
                "route_table_id": route_table.get("id"),
                "route_table_attached": bool(
                    route_table.get("id")
                ),
                "delegations": [
                    delegation.get("properties", {}).get(
                        "serviceName"
                    )
                    for delegation in delegations
                ],
                "private_endpoint_network_policies": (
                    private_endpoint_policies
                ),
                "private_link_service_network_policies": (
                    private_link_service_policies
                ),
                "resource_id": subnet_data.get("id"),
            },
        )

        self.log_complete()
        return tool_result