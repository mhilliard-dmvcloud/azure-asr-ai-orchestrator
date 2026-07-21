from typing import Any

from core.base_tool import BaseTool
from models.tool_result import ToolResult
from services.azure_resource_service import AzureResourceService


class SourceVmEligibilityTool(BaseTool):
    """Discovers a source VM and performs core ASR eligibility checks."""

    API_VERSION = "2025-04-01"

    MAX_OS_DISK_SIZE_GB = 4095
    MAX_DATA_DISK_SIZE_GB = 32768
    MAX_DATA_DISK_COUNT = 64

    def __init__(self, azure_service: AzureResourceService):
        super().__init__(
            name="check_source_vm_eligibility",
            description=(
                "Discovers the source Azure VM and checks its region, "
                "runtime state, generation, disk configuration, "
                "encryption settings, and ephemeral OS-disk status."
            ),
        )

        self.azure_service = azure_service

    @staticmethod
    def _normalize_location(value: str) -> str:
        return value.strip().lower().replace(" ", "")

    @staticmethod
    def _get_status_value(
        statuses: list[dict[str, Any]],
        prefix: str,
    ) -> str | None:
        """Return the display status whose code begins with a prefix."""

        normalized_prefix = prefix.lower()

        for status in statuses:
            code = str(status.get("code", "")).lower()

            if code.startswith(normalized_prefix):
                return (
                    status.get("displayStatus")
                    or status.get("code")
                )

        return None

    @staticmethod
    def _disk_is_managed(
        disk: dict[str, Any],
    ) -> bool:
        managed_disk = disk.get("managedDisk") or {}

        return bool(managed_disk.get("id"))

    @staticmethod
    def _disk_encryption_details(
        disk: dict[str, Any],
    ) -> dict[str, Any]:
        managed_disk = disk.get("managedDisk") or {}
        disk_encryption_set = (
            managed_disk.get("diskEncryptionSet") or {}
        )

        encryption_settings = (
            disk.get("encryptionSettings") or {}
        )

        return {
            "disk_encryption_set_id": (
                disk_encryption_set.get("id")
            ),
            "customer_managed_key_configured": bool(
                disk_encryption_set.get("id")
            ),
            "azure_disk_encryption_enabled": (
                encryption_settings.get("enabled")
            ),
        }

    def _build_disk_details(
        self,
        disk: dict[str, Any],
        disk_role: str,
    ) -> dict[str, Any]:
        managed_disk = disk.get("managedDisk") or {}

        details = {
            "role": disk_role,
            "name": disk.get("name"),
            "lun": disk.get("lun"),
            "disk_size_gb": disk.get("diskSizeGB"),
            "caching": disk.get("caching"),
            "write_accelerator_enabled": disk.get(
                "writeAcceleratorEnabled"
            ),
            "managed": self._disk_is_managed(disk),
            "managed_disk_id": managed_disk.get("id"),
            "storage_account_type": managed_disk.get(
                "storageAccountType"
            ),
            "delete_option": disk.get("deleteOption"),
        }

        details.update(
            self._disk_encryption_details(disk)
        )

        return details

    def execute(self, **kwargs) -> ToolResult:
        resource_group_name = kwargs.get(
            "resource_group_name",
            "",
        ).strip()

        vm_name = kwargs.get(
            "vm_name",
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
                    "Source VM resource group cannot be empty."
                ),
            )

        if not vm_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Source VM name cannot be empty.",
            )

        self.log_start()

        path = (
            f"/subscriptions/{self.azure_service.subscription_id}"
            f"/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.Compute"
            f"/virtualMachines/{vm_name}"
        )

        result = self.azure_service.get(
            path=path,
            api_version=self.API_VERSION,
            query_params={
                "$expand": "instanceView",
            },
        )

        if not result["found"]:
            tool_result = ToolResult(
                tool_name=self.name,
                status="not_found",
                severity="warning",
                message=(
                    f"Source VM '{vm_name}' was not found in "
                    f"resource group '{resource_group_name}'."
                ),
                data={
                    "vm_name": vm_name,
                    "resource_group_name": resource_group_name,
                    "exists": False,
                    "eligible": False,
                },
            )

            self.log_complete()
            return tool_result

        vm_data = result.get("data") or {}
        properties = vm_data.get("properties") or {}

        hardware_profile = (
            properties.get("hardwareProfile") or {}
        )

        storage_profile = (
            properties.get("storageProfile") or {}
        )

        security_profile = (
            properties.get("securityProfile") or {}
        )

        instance_view = (
            properties.get("instanceView") or {}
        )

        instance_statuses = (
            instance_view.get("statuses") or []
        )

        actual_location = self._normalize_location(
            vm_data.get("location", "")
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

        power_state = self._get_status_value(
            statuses=instance_statuses,
            prefix="powerstate/",
        )

        hyper_v_generation = (
            instance_view.get("hyperVGeneration")
        )

        os_disk = storage_profile.get("osDisk") or {}
        data_disks = storage_profile.get("dataDisks") or []

        os_disk_details = self._build_disk_details(
            disk=os_disk,
            disk_role="os",
        )

        data_disk_details = [
            self._build_disk_details(
                disk=disk,
                disk_role="data",
            )
            for disk in data_disks
        ]

        diff_disk_settings = (
            os_disk.get("diffDiskSettings") or {}
        )

        diff_disk_option = diff_disk_settings.get(
            "option"
        )

        ephemeral_os_disk = (
            str(diff_disk_option).lower() == "local"
        )

        ephemeral_placement = (
            diff_disk_settings.get("placement")
        )

        os_disk_size_gb = os_disk.get("diskSizeGB")
        os_disk_size_supported = (
            os_disk_size_gb is None
            or os_disk_size_gb <= self.MAX_OS_DISK_SIZE_GB
        )

        oversized_data_disks = [
            {
                "name": disk.get("name"),
                "disk_size_gb": disk.get("diskSizeGB"),
            }
            for disk in data_disks
            if (
                disk.get("diskSizeGB") is not None
                and disk.get("diskSizeGB")
                > self.MAX_DATA_DISK_SIZE_GB
            )
        ]

        data_disk_count_supported = (
            len(data_disks)
            <= self.MAX_DATA_DISK_COUNT
        )

        unmanaged_disks = []

        if not self._disk_is_managed(os_disk):
            unmanaged_disks.append(
                os_disk.get("name") or "OS disk"
            )

        unmanaged_disks.extend(
            disk.get("name") or f"LUN {disk.get('lun')}"
            for disk in data_disks
            if not self._disk_is_managed(disk)
        )

        disk_encryption_set_ids = [
            disk["disk_encryption_set_id"]
            for disk in (
                [os_disk_details] + data_disk_details
            )
            if disk.get("disk_encryption_set_id")
        ]

        azure_disk_encryption_detected = any(
            disk.get("azure_disk_encryption_enabled") is True
            for disk in (
                [os_disk_details] + data_disk_details
            )
        )

        encryption_at_host = security_profile.get(
            "encryptionAtHost"
        )

        security_type = security_profile.get(
            "securityType"
        )

        blocking_findings = []
        warning_findings = []
        informational_findings = []

        if not location_matches:
            blocking_findings.append(
                "VM location does not match the supplied source region."
            )

        if not provisioning_succeeded:
            blocking_findings.append(
                "VM provisioning state is not Succeeded."
            )

        if ephemeral_os_disk:
            blocking_findings.append(
                "VM uses an ephemeral OS disk, which Azure Site "
                "Recovery does not support."
            )

        if not os_disk_size_supported:
            blocking_findings.append(
                "OS disk exceeds the supported Site Recovery size."
            )

        if oversized_data_disks:
            blocking_findings.append(
                "One or more data disks exceed the supported "
                "Site Recovery size."
            )

        if not data_disk_count_supported:
            blocking_findings.append(
                "VM has more than 64 data disks."
            )

        if unmanaged_disks:
            warning_findings.append(
                "One or more disks are not managed disks."
            )

        if encryption_at_host:
            warning_findings.append(
                "Encryption at host is enabled. Validate the "
                "target-state behavior during failover design."
            )

        if power_state not in {
            "VM running",
            "PowerState/running",
        }:
            warning_findings.append(
                "VM is not currently reported as running."
            )

        if disk_encryption_set_ids:
            informational_findings.append(
                "Customer-managed disk encryption is configured."
            )

        if azure_disk_encryption_detected:
            informational_findings.append(
                "Azure Disk Encryption settings were detected."
            )

        if security_type:
            informational_findings.append(
                f"VM security type is '{security_type}'."
            )

        eligible = not blocking_findings

        if blocking_findings:
            status = "validation_failed"
            severity = "warning"
            message = (
                f"Source VM '{vm_name}' was found, but it failed "
                "one or more core Site Recovery eligibility checks."
            )

        elif warning_findings:
            status = "validation_failed"
            severity = "warning"
            message = (
                f"Source VM '{vm_name}' passed the blocking checks, "
                "but one or more configuration warnings require review."
            )

        else:
            status = "success"
            severity = "info"
            message = (
                f"Source VM '{vm_name}' was found and passed the "
                "core Site Recovery eligibility checks."
            )

        tool_result = ToolResult(
            tool_name=self.name,
            status=status,
            severity=severity,
            message=message,
            data={
                "vm_name": vm_name,
                "resource_group_name": resource_group_name,
                "exists": True,
                "eligible": eligible,
                "location": actual_location,
                "expected_location": expected_location or None,
                "location_matches": location_matches,
                "vm_size": hardware_profile.get("vmSize"),
                "provisioning_state": provisioning_state,
                "power_state": power_state,
                "hyper_v_generation": hyper_v_generation,
                "zones": vm_data.get("zones") or [],
                "os_type": os_disk.get("osType"),
                "license_type": properties.get("licenseType"),
                "security_type": security_type,
                "encryption_at_host": encryption_at_host,
                "ephemeral_os_disk": ephemeral_os_disk,
                "ephemeral_disk_option": diff_disk_option,
                "ephemeral_disk_placement": ephemeral_placement,
                "os_disk": os_disk_details,
                "data_disk_count": len(data_disks),
                "data_disks": data_disk_details,
                "data_disk_count_supported": (
                    data_disk_count_supported
                ),
                "oversized_data_disks": oversized_data_disks,
                "unmanaged_disks": unmanaged_disks,
                "customer_managed_key_configured": bool(
                    disk_encryption_set_ids
                ),
                "disk_encryption_set_ids": list(
                    dict.fromkeys(disk_encryption_set_ids)
                ),
                "azure_disk_encryption_detected": (
                    azure_disk_encryption_detected
                ),
                "blocking_findings": blocking_findings,
                "warning_findings": warning_findings,
                "informational_findings": informational_findings,
                "resource_id": vm_data.get("id"),
                "validation_scope": (
                    "Control-plane and instance-view eligibility "
                    "checks only. Guest OS support, churn rate, "
                    "subscription quotas, protected-disk limits, "
                    "extension health, and effective connectivity "
                    "require additional tools."
                ),
            },
        )

        self.log_complete()
        return tool_result