from core.base_tool import BaseTool
from models.tool_result import ToolResult
from services.azure_resource_service import AzureResourceService


class RecoveryServicesVaultTool(BaseTool):
    """Checks whether a Recovery Services vault exists."""

    API_VERSION = "2026-02-01"

    def __init__(self, azure_service: AzureResourceService):
        super().__init__(
            name="check_recovery_services_vault",
            description=(
                "Checks whether a Recovery Services vault exists and "
                "validates its location, provisioning state, SKU, "
                "managed identity, and public network access."
            ),
        )

        self.azure_service = azure_service

    def execute(self, **kwargs) -> ToolResult:
        resource_group_name = kwargs.get(
            "resource_group_name",
            "",
        ).strip()

        vault_name = kwargs.get(
            "vault_name",
            "",
        ).strip()

        expected_location = kwargs.get(
            "expected_location",
            "",
        ).strip().lower().replace(" ", "")

        if not resource_group_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Resource group name cannot be empty.",
            )

        if not vault_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Recovery Services vault name cannot be empty.",
            )

        self.log_start()

        path = (
            f"/subscriptions/{self.azure_service.subscription_id}"
            f"/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.RecoveryServices"
            f"/vaults/{vault_name}"
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
                    f"Recovery Services vault '{vault_name}' "
                    f"was not found in resource group "
                    f"'{resource_group_name}'."
                ),
                data={
                    "vault_name": vault_name,
                    "resource_group_name": resource_group_name,
                    "exists": False,
                },
            )

            self.log_complete()
            return tool_result

        vault_data = result.get("data") or {}
        properties = vault_data.get("properties") or {}
        identity = vault_data.get("identity") or {}
        sku = vault_data.get("sku") or {}

        actual_location = (
            vault_data.get("location", "")
            .lower()
            .replace(" ", "")
        )

        location_matches = (
            not expected_location
            or actual_location == expected_location
        )

        managed_identity_enabled = (
            identity.get("type") is not None
            and identity.get("type") != "None"
        )

        status = "success" if location_matches else "validation_failed"
        severity = "info" if location_matches else "warning"

        if location_matches:
            message = (
                f"Recovery Services vault '{vault_name}' was found "
                "and passed the location check."
            )
        else:
            message = (
                f"Recovery Services vault '{vault_name}' was found, "
                f"but its location '{actual_location}' does not match "
                f"the expected location '{expected_location}'."
            )

        tool_result = ToolResult(
            tool_name=self.name,
            status=status,
            severity=severity,
            message=message,
            data={
                "vault_name": vault_name,
                "resource_group_name": resource_group_name,
                "exists": True,
                "location": actual_location,
                "expected_location": expected_location or None,
                "location_matches": location_matches,
                "provisioning_state": properties.get(
                    "provisioningState"
                ),
                "sku_name": sku.get("name"),
                "managed_identity_enabled": managed_identity_enabled,
                "managed_identity_type": identity.get("type"),
                "public_network_access": properties.get(
                    "publicNetworkAccess"
                ),
                "resource_id": vault_data.get("id"),
            },
        )

        self.log_complete()

        return tool_result