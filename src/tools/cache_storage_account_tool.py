from core.base_tool import BaseTool
from models.tool_result import ToolResult
from services.azure_resource_service import AzureResourceService


class CacheStorageAccountTool(BaseTool):
    """Checks an Azure Site Recovery cache storage account."""

    API_VERSION = "2025-01-01"

    def __init__(self, azure_service: AzureResourceService):
        super().__init__(
            name="check_cache_storage_account",
            description=(
                "Checks whether an Azure Storage account exists and "
                "validates its region, provisioning state, account kind, "
                "SKU, HTTPS enforcement, and network access."
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

        storage_account_name = kwargs.get(
            "storage_account_name",
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
                message=(
                    "Cache storage resource group cannot be empty."
                ),
            )

        if not storage_account_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message=(
                    "Cache storage account name cannot be empty."
                ),
            )

        self.log_start()

        path = (
            f"/subscriptions/{self.azure_service.subscription_id}"
            f"/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.Storage"
            f"/storageAccounts/{storage_account_name}"
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
                    f"Cache storage account "
                    f"'{storage_account_name}' was not found in "
                    f"resource group '{resource_group_name}'."
                ),
                data={
                    "storage_account_name": storage_account_name,
                    "resource_group_name": resource_group_name,
                    "exists": False,
                },
            )

            self.log_complete()
            return tool_result

        storage_data = result.get("data") or {}
        properties = storage_data.get("properties") or {}
        sku = storage_data.get("sku") or {}

        actual_location = self._normalize_location(
            storage_data.get("location", "")
        )

        location_matches = (
            not expected_location
            or actual_location == expected_location
        )

        account_kind = storage_data.get("kind")
        supported_kinds = {
            "StorageV2",
            "BlockBlobStorage",
            "Storage",
        }
        kind_supported = account_kind in supported_kinds

        provisioning_state = properties.get(
            "provisioningState"
        )
        provisioning_succeeded = (
            provisioning_state == "Succeeded"
        )

        https_only = properties.get(
            "supportsHttpsTrafficOnly"
        )

        public_network_access = properties.get(
            "publicNetworkAccess"
        )

        minimum_tls_version = properties.get(
            "minimumTlsVersion"
        )

        checks_passed = (
            location_matches
            and kind_supported
            and provisioning_succeeded
        )

        if checks_passed:
            status = "success"
            severity = "info"
            message = (
                f"Cache storage account "
                f"'{storage_account_name}' was found and passed "
                "the core Site Recovery cache checks."
            )
        else:
            status = "validation_failed"
            severity = "warning"

            failed_checks = []

            if not location_matches:
                failed_checks.append(
                    "storage account is not in the source region"
                )

            if not kind_supported:
                failed_checks.append(
                    f"account kind '{account_kind}' is unsupported"
                )

            if not provisioning_succeeded:
                failed_checks.append(
                    "provisioning state is not Succeeded"
                )

            message = (
                f"Cache storage account "
                f"'{storage_account_name}' was found, but "
                + "; ".join(failed_checks)
                + "."
            )

        tool_result = ToolResult(
            tool_name=self.name,
            status=status,
            severity=severity,
            message=message,
            data={
                "storage_account_name": storage_account_name,
                "resource_group_name": resource_group_name,
                "exists": True,
                "location": actual_location,
                "expected_location": (
                    expected_location or None
                ),
                "location_matches": location_matches,
                "kind": account_kind,
                "kind_supported": kind_supported,
                "sku_name": sku.get("name"),
                "sku_tier": sku.get("tier"),
                "provisioning_state": provisioning_state,
                "https_only": https_only,
                "minimum_tls_version": minimum_tls_version,
                "public_network_access": public_network_access,
                "allow_blob_public_access": properties.get(
                    "allowBlobPublicAccess"
                ),
                "resource_id": storage_data.get("id"),
            },
        )

        self.log_complete()
        return tool_result