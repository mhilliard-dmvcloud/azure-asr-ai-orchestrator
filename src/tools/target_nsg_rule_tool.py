from typing import Any

from core.base_tool import BaseTool
from models.tool_result import ToolResult
from services.azure_resource_service import AzureResourceService


class TargetNsgRuleTool(BaseTool):
    """
    Checks the NSG attached to the target subnet and validates
    Azure Site Recovery outbound HTTPS rules.
    """

    API_VERSION = "2025-05-01"

    def __init__(self, azure_service: AzureResourceService):
        super().__init__(
            name="check_target_nsg_rules",
            description=(
                "Discovers the NSG attached to the target subnet and "
                "checks for outbound HTTPS rules required by Azure "
                "Site Recovery."
            ),
        )

        self.azure_service = azure_service

    @staticmethod
    def _normalize_region(value: str) -> str:
        return value.strip().replace(" ", "")

    @staticmethod
    def _normalize_value(value: str | None) -> str:
        return (value or "").strip().lower().replace(" ", "")

    @staticmethod
    def _extract_resource_details(
        resource_id: str,
    ) -> tuple[str, str]:
        """
        Extract the resource-group and NSG names from an Azure resource ID.
        """

        parts = [
            part
            for part in resource_id.strip("/").split("/")
            if part
        ]

        lowered_parts = [part.lower() for part in parts]

        try:
            resource_group_index = lowered_parts.index(
                "resourcegroups"
            )
            nsg_index = lowered_parts.index(
                "networksecuritygroups"
            )

            resource_group_name = parts[
                resource_group_index + 1
            ]
            nsg_name = parts[nsg_index + 1]

        except (ValueError, IndexError) as error:
            raise ValueError(
                f"Unable to parse NSG resource ID: {resource_id}"
            ) from error

        return resource_group_name, nsg_name

    @staticmethod
    def _get_rule_values(
        properties: dict[str, Any],
        singular_name: str,
        plural_name: str,
    ) -> list[str]:
        """
        Return either a plural rule property or its singular equivalent.
        """

        plural_values = properties.get(plural_name)

        if isinstance(plural_values, list):
            return [
                str(value)
                for value in plural_values
                if value is not None
            ]

        singular_value = properties.get(singular_name)

        if singular_value is None:
            return []

        return [str(singular_value)]

    def _rule_allows_destination(
        self,
        rule: dict[str, Any],
        destination_tag: str,
    ) -> bool:
        """
        Determine whether a custom NSG rule explicitly allows outbound
        TCP/HTTPS traffic to the requested destination service tag.
        """

        properties = rule.get("properties") or {}

        direction = self._normalize_value(
            properties.get("direction")
        )
        access = self._normalize_value(
            properties.get("access")
        )
        protocol = self._normalize_value(
            properties.get("protocol")
        )

        if direction != "outbound":
            return False

        if access != "allow":
            return False

        if protocol not in {"tcp", "*", "any"}:
            return False

        destination_prefixes = self._get_rule_values(
            properties=properties,
            singular_name="destinationAddressPrefix",
            plural_name="destinationAddressPrefixes",
        )

        destination_ports = self._get_rule_values(
            properties=properties,
            singular_name="destinationPortRange",
            plural_name="destinationPortRanges",
        )

        normalized_destination_tag = self._normalize_value(
            destination_tag
        )

        destination_matches = any(
            self._normalize_value(prefix)
            == normalized_destination_tag
            for prefix in destination_prefixes
        )

        port_matches = any(
            port.strip() in {"443", "*"}
            for port in destination_ports
        )

        return destination_matches and port_matches

    def execute(self, **kwargs) -> ToolResult:
        target_resource_group = kwargs.get(
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

        source_region = self._normalize_region(
            kwargs.get("source_region", "")
        )

        target_region = self._normalize_region(
            kwargs.get("target_region", "")
        )

        if not target_resource_group:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message=(
                    "Target network resource group cannot be empty."
                ),
            )

        if not virtual_network_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Target virtual network cannot be empty.",
            )

        if not subnet_name:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message="Target subnet cannot be empty.",
            )

        if not source_region or not target_region:
            return ToolResult(
                tool_name=self.name,
                status="failed",
                severity="error",
                message=(
                    "Source and target regions are required for "
                    "the NSG Site Recovery rule check."
                ),
            )

        self.log_start()

        # First retrieve the subnet to discover its attached NSG.
        subnet_path = (
            f"/subscriptions/{self.azure_service.subscription_id}"
            f"/resourceGroups/{target_resource_group}"
            f"/providers/Microsoft.Network"
            f"/virtualNetworks/{virtual_network_name}"
            f"/subnets/{subnet_name}"
        )

        subnet_result = self.azure_service.get(
            path=subnet_path,
            api_version=self.API_VERSION,
        )

        if not subnet_result["found"]:
            tool_result = ToolResult(
                tool_name=self.name,
                status="not_found",
                severity="warning",
                message=(
                    f"Target subnet '{subnet_name}' was not found, "
                    "so its attached NSG could not be evaluated."
                ),
                data={
                    "resource_group_name": target_resource_group,
                    "virtual_network_name": virtual_network_name,
                    "subnet_name": subnet_name,
                    "subnet_exists": False,
                },
            )

            self.log_complete()
            return tool_result

        subnet_data = subnet_result.get("data") or {}
        subnet_properties = subnet_data.get("properties") or {}

        nsg_reference = (
            subnet_properties.get("networkSecurityGroup") or {}
        )

        nsg_resource_id = nsg_reference.get("id")

        if not nsg_resource_id:
            tool_result = ToolResult(
                tool_name=self.name,
                status="validation_failed",
                severity="warning",
                message=(
                    f"Target subnet '{subnet_name}' does not have "
                    "an attached network security group."
                ),
                data={
                    "resource_group_name": target_resource_group,
                    "virtual_network_name": virtual_network_name,
                    "subnet_name": subnet_name,
                    "subnet_exists": True,
                    "nsg_attached": False,
                    "required_service_tags": [
                        f"Storage.{target_region}",
                        "AzureActiveDirectory",
                        f"EventHub.{source_region}",
                        "AzureSiteRecovery",
                    ],
                },
            )

            self.log_complete()
            return tool_result

        nsg_resource_group, nsg_name = (
            self._extract_resource_details(nsg_resource_id)
        )

        nsg_path = (
            f"/subscriptions/{self.azure_service.subscription_id}"
            f"/resourceGroups/{nsg_resource_group}"
            f"/providers/Microsoft.Network"
            f"/networkSecurityGroups/{nsg_name}"
        )

        nsg_result = self.azure_service.get(
            path=nsg_path,
            api_version=self.API_VERSION,
        )

        if not nsg_result["found"]:
            tool_result = ToolResult(
                tool_name=self.name,
                status="not_found",
                severity="warning",
                message=(
                    f"The subnet references NSG '{nsg_name}', but "
                    "the NSG could not be retrieved."
                ),
                data={
                    "subnet_name": subnet_name,
                    "nsg_attached": True,
                    "nsg_name": nsg_name,
                    "nsg_resource_group": nsg_resource_group,
                    "nsg_resource_id": nsg_resource_id,
                },
            )

            self.log_complete()
            return tool_result

        nsg_data = nsg_result.get("data") or {}
        nsg_properties = nsg_data.get("properties") or {}

        custom_rules = nsg_properties.get(
            "securityRules"
        ) or []

        required_destinations = [
            f"Storage.{target_region}",
            "AzureActiveDirectory",
            f"EventHub.{source_region}",
            "AzureSiteRecovery",
        ]

        rule_results: list[dict[str, Any]] = []

        for destination in required_destinations:
            matching_rules = [
                rule
                for rule in custom_rules
                if self._rule_allows_destination(
                    rule=rule,
                    destination_tag=destination,
                )
            ]

            rule_results.append(
                {
                    "destination_service_tag": destination,
                    "port": "443",
                    "direction": "Outbound",
                    "explicit_allow_rule_found": bool(
                        matching_rules
                    ),
                    "matching_rule_names": [
                        rule.get("name")
                        for rule in matching_rules
                    ],
                }
            )

        missing_destinations = [
            result["destination_service_tag"]
            for result in rule_results
            if not result["explicit_allow_rule_found"]
        ]

        provisioning_state = nsg_properties.get(
            "provisioningState"
        )

        checks_passed = (
            provisioning_state == "Succeeded"
            and not missing_destinations
        )

        if checks_passed:
            status = "success"
            severity = "info"
            message = (
                f"NSG '{nsg_name}' is attached to target subnet "
                f"'{subnet_name}' and contains explicit outbound "
                "HTTPS rules for the required Site Recovery "
                "service tags."
            )
        else:
            status = "validation_failed"
            severity = "warning"

            if missing_destinations:
                message = (
                    f"NSG '{nsg_name}' is attached to target subnet "
                    f"'{subnet_name}', but explicit outbound HTTPS "
                    "rules were not found for: "
                    + ", ".join(missing_destinations)
                    + "."
                )
            else:
                message = (
                    f"NSG '{nsg_name}' was found, but its "
                    f"provisioning state is "
                    f"'{provisioning_state}'."
                )

        tool_result = ToolResult(
            tool_name=self.name,
            status=status,
            severity=severity,
            message=message,
            data={
                "resource_group_name": target_resource_group,
                "virtual_network_name": virtual_network_name,
                "subnet_name": subnet_name,
                "subnet_exists": True,
                "nsg_attached": True,
                "nsg_name": nsg_name,
                "nsg_resource_group": nsg_resource_group,
                "nsg_resource_id": nsg_resource_id,
                "nsg_location": nsg_data.get("location"),
                "provisioning_state": provisioning_state,
                "custom_rule_count": len(custom_rules),
                "required_rules": rule_results,
                "missing_destinations": missing_destinations,
                "all_explicit_rules_found": (
                    not missing_destinations
                ),
                "validation_scope": (
                    "Custom NSG configuration only. This result does "
                    "not calculate effective rules across NIC NSGs, "
                    "Azure Firewall, route tables, or NVAs."
                ),
            },
        )

        self.log_complete()
        return tool_result