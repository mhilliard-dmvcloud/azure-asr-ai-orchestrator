from core.base_tool import BaseTool
from models.tool_result import ToolResult
from services.azure_resource_service import AzureResourceService


class ResourceGroupTool(BaseTool):
    """Checks whether an Azure resource group exists."""

    API_VERSION = "2021-04-01"

    def __init__(self, azure_service: AzureResourceService):
        super().__init__(
            name="check_resource_group",
            description=(
                "Checks whether an Azure resource group exists and "
                "returns its location and provisioning state."
            ),
        )

        self.azure_service = azure_service

    def execute(self, **kwargs) -> ToolResult:
        resource_group_name = kwargs.get(
            "resource_group_name",
            "",
        ).strip()

        if not resource_group_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Resource group name cannot be empty.",
            )

        self.log_start()

        path = (
            f"/subscriptions/{self.azure_service.subscription_id}"
            f"/resourcegroups/{resource_group_name}"
        )

        result = self.azure_service.get(
            path=path,
            api_version=self.API_VERSION,
        )

        resource_data = result.get("data") or {}

        if not result["found"]:
            tool_result = ToolResult(
                tool_name=self.name,
                status="not_found",
                severity="warning",
                message=(
                    f"Resource group '{resource_group_name}' "
                    "was not found."
                ),
                data={
                    "resource_group_name": resource_group_name,
                    "exists": False,
                },
            )
        else:
            tool_result = ToolResult(
                tool_name=self.name,
                status="success",
                severity="info",
                message=(
                    f"Resource group '{resource_group_name}' was found."
                ),
                data={
                    "resource_group_name": resource_group_name,
                    "exists": True,
                    "location": resource_data.get("location"),
                    "provisioning_state": (
                        resource_data
                        .get("properties", {})
                        .get("provisioningState")
                    ),
                },
            )

        self.log_complete()

        return tool_result