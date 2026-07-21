from core.base_tool import BaseTool
from models.tool_result import ToolResult
from services.azure_resource_service import AzureResourceService


class TargetVirtualNetworkTool(BaseTool):
    """Checks the target Azure virtual network."""

    API_VERSION = "2025-05-01"

    def __init__(self, azure_service: AzureResourceService):
        super().__init__(
            name="check_target_virtual_network",
            description=(
                "Checks whether the target virtual network exists and "
                "validates its location and provisioning state."
            ),
        )
        self.azure_service = azure_service

    @staticmethod
    def _normalize_location(value: str) -> str:
        return value.strip().lower().replace(" ", "")

    def execute(self, **kwargs) -> ToolResult:
        resource_group_name = kwargs.get(
            "resource_group_name",
            "",
        ).strip()

        virtual_network_name = kwargs.get(
            "virtual_network_name",
            "",
        ).strip()

        expected_location = self._normalize_location(
            kwargs.get("expected_location", "")
        )

        if not resource_group_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Target VNet resource group cannot be empty.",
            )

        if not virtual_network_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Target virtual network name cannot be empty.",
            )

        self.log_start()

        path = (
            f"/subscriptions/{self.azure_service.subscription_id}"
            f"/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.Network"
            f"/virtualNetworks/{virtual_network_name}"
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
                    f"Target virtual network "
                    f"'{virtual_network_name}' was not found in "
                    f"resource group '{resource_group_name}'."
                ),
                data={
                    "virtual_network_name": virtual_network_name,
                    "resource_group_name": resource_group_name,
                    "exists": False,
                },
            )

            self.log_complete()
            return tool_result

        vnet_data = result.get("data") or {}
        properties = vnet_data.get("properties") or {}

        actual_location = self._normalize_location(
            vnet_data.get("location", "")
        )

        location_matches = (
            not expected_location
            or actual_location == expected_location
        )

        provisioning_state = properties.get(
            "provisioningState"
        )

        provisioning_succeeded = (
            provisioning_state == "Succeeded"
        )

        address_space = (
            properties.get("addressSpace", {})
            .get("addressPrefixes", [])
        )

        subnets = properties.get("subnets") or []

        checks_passed = (
            location_matches
            and provisioning_succeeded
            and bool(address_space)
        )

        if checks_passed:
            status = "success"
            severity = "info"
            message = (
                f"Target virtual network "
                f"'{virtual_network_name}' was found and passed "
                "the core network checks."
            )
        else:
            status = "validation_failed"
            severity = "warning"

            failed_checks = []

            if not location_matches:
                failed_checks.append(
                    "VNet is not in the expected target region"
                )

            if not provisioning_succeeded:
                failed_checks.append(
                    "provisioning state is not Succeeded"
                )

            if not address_space:
                failed_checks.append(
                    "no address space was returned"
                )

            message = (
                f"Target virtual network "
                f"'{virtual_network_name}' was found, but "
                + "; ".join(failed_checks)
                + "."
            )

        tool_result = ToolResult(
            tool_name=self.name,
            status=status,
            severity=severity,
            message=message,
            data={
                "virtual_network_name": virtual_network_name,
                "resource_group_name": resource_group_name,
                "exists": True,
                "location": actual_location,
                "expected_location": expected_location or None,
                "location_matches": location_matches,
                "provisioning_state": provisioning_state,
                "address_prefixes": address_space,
                "subnet_count": len(subnets),
                "subnet_names": [
                    subnet.get("name")
                    for subnet in subnets
                ],
                "resource_id": vnet_data.get("id"),
            },
        )

        self.log_complete()
        return tool_result