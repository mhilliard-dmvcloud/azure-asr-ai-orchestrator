from typing import Any

from core.base_tool import BaseTool
from models.tool_result import ToolResult
from services.azure_resource_service import AzureResourceService


class SourceVmNetworkTool(BaseTool):
    """Discovers the source VM NICs and prepares network mapping."""

    COMPUTE_API_VERSION = "2025-04-01"
    NETWORK_API_VERSION = "2025-05-01"

    def __init__(self, azure_service: AzureResourceService):
        super().__init__(
            name="check_source_vm_network_interfaces",
            description=(
                "Discovers every NIC and IP configuration attached to "
                "the source VM, identifies the primary NIC, validates "
                "source subnet information, and prepares target network "
                "mapping recommendations."
            ),
        )

        self.azure_service = azure_service

    @staticmethod
    def _parse_resource_id(
        resource_id: str,
    ) -> dict[str, str]:
        """Extract common values from an Azure resource ID."""

        parts = [
            part
            for part in resource_id.strip("/").split("/")
            if part
        ]

        lowered = [part.lower() for part in parts]

        result: dict[str, str] = {
            "subscription_id": "",
            "resource_group_name": "",
            "provider_namespace": "",
            "resource_type": "",
            "resource_name": "",
        }

        try:
            subscription_index = lowered.index("subscriptions")
            result["subscription_id"] = parts[
                subscription_index + 1
            ]
        except (ValueError, IndexError):
            pass

        try:
            resource_group_index = lowered.index(
                "resourcegroups"
            )
            result["resource_group_name"] = parts[
                resource_group_index + 1
            ]
        except (ValueError, IndexError):
            pass

        try:
            provider_index = lowered.index("providers")
            result["provider_namespace"] = parts[
                provider_index + 1
            ]
            result["resource_type"] = parts[
                provider_index + 2
            ]
            result["resource_name"] = parts[
                provider_index + 3
            ]
        except (ValueError, IndexError):
            pass

        return result

    @staticmethod
    def _parse_subnet_id(
        subnet_id: str,
    ) -> dict[str, str]:
        """Extract the VNet, subnet, and resource group names."""

        parts = [
            part
            for part in subnet_id.strip("/").split("/")
            if part
        ]

        lowered = [part.lower() for part in parts]

        result = {
            "resource_group_name": "",
            "virtual_network_name": "",
            "subnet_name": "",
        }

        try:
            rg_index = lowered.index("resourcegroups")
            result["resource_group_name"] = parts[rg_index + 1]
        except (ValueError, IndexError):
            pass

        try:
            vnet_index = lowered.index("virtualnetworks")
            result["virtual_network_name"] = parts[
                vnet_index + 1
            ]
        except (ValueError, IndexError):
            pass

        try:
            subnet_index = lowered.index("subnets")
            result["subnet_name"] = parts[subnet_index + 1]
        except (ValueError, IndexError):
            pass

        return result

    @staticmethod
    def _normalize_location(value: str) -> str:
        return value.strip().lower().replace(" ", "")

    def _get_nic(
        self,
        nic_resource_id: str,
    ) -> dict[str, Any] | None:
        nic_details = self._parse_resource_id(
            nic_resource_id
        )

        nic_resource_group = nic_details.get(
            "resource_group_name",
            "",
        )

        nic_name = nic_details.get(
            "resource_name",
            "",
        )

        if not nic_resource_group or not nic_name:
            raise ValueError(
                f"Unable to parse NIC resource ID: "
                f"{nic_resource_id}"
            )

        path = (
            f"/subscriptions/{self.azure_service.subscription_id}"
            f"/resourceGroups/{nic_resource_group}"
            f"/providers/Microsoft.Network"
            f"/networkInterfaces/{nic_name}"
        )

        result = self.azure_service.get(
            path=path,
            api_version=self.NETWORK_API_VERSION,
        )

        if not result["found"]:
            return None

        return result.get("data") or {}

    def _build_ip_configuration(
        self,
        ip_configuration: dict[str, Any],
    ) -> dict[str, Any]:
        properties = ip_configuration.get("properties") or {}

        subnet_reference = properties.get("subnet") or {}
        subnet_id = subnet_reference.get("id") or ""

        subnet_details = (
            self._parse_subnet_id(subnet_id)
            if subnet_id
            else {
                "resource_group_name": "",
                "virtual_network_name": "",
                "subnet_name": "",
            }
        )

        public_ip_reference = (
            properties.get("publicIPAddress") or {}
        )

        application_gateway_pools = properties.get(
            "applicationGatewayBackendAddressPools"
        ) or []

        load_balancer_pools = properties.get(
            "loadBalancerBackendAddressPools"
        ) or []

        return {
            "name": ip_configuration.get("name"),
            "primary": properties.get("primary", False),
            "private_ip_address": properties.get(
                "privateIPAddress"
            ),
            "private_ip_allocation_method": properties.get(
                "privateIPAllocationMethod"
            ),
            "private_ip_version": properties.get(
                "privateIPAddressVersion"
            ),
            "subnet_id": subnet_id or None,
            "source_vnet_resource_group": (
                subnet_details["resource_group_name"] or None
            ),
            "source_vnet_name": (
                subnet_details["virtual_network_name"] or None
            ),
            "source_subnet_name": (
                subnet_details["subnet_name"] or None
            ),
            "public_ip_address_id": (
                public_ip_reference.get("id")
            ),
            "public_ip_attached": bool(
                public_ip_reference.get("id")
            ),
            "application_gateway_backend_pool_ids": [
                pool.get("id")
                for pool in application_gateway_pools
                if pool.get("id")
            ],
            "load_balancer_backend_pool_ids": [
                pool.get("id")
                for pool in load_balancer_pools
                if pool.get("id")
            ],
            "provisioning_state": properties.get(
                "provisioningState"
            ),
        }

    def execute(self, **kwargs) -> ToolResult:
        resource_group_name = kwargs.get(
            "resource_group_name",
            "",
        ).strip()

        vm_name = kwargs.get(
            "vm_name",
            "",
        ).strip()

        expected_source_location = self._normalize_location(
            kwargs.get("expected_source_location", "")
        )

        target_resource_group = kwargs.get(
            "target_resource_group",
            "",
        ).strip()

        target_vnet = kwargs.get(
            "target_vnet",
            "",
        ).strip()

        target_subnet = kwargs.get(
            "target_subnet",
            "",
        ).strip()

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

        vm_path = (
            f"/subscriptions/{self.azure_service.subscription_id}"
            f"/resourceGroups/{resource_group_name}"
            f"/providers/Microsoft.Compute"
            f"/virtualMachines/{vm_name}"
        )

        vm_result = self.azure_service.get(
            path=vm_path,
            api_version=self.COMPUTE_API_VERSION,
        )

        if not vm_result["found"]:
            tool_result = ToolResult(
                tool_name=self.name,
                status="not_found",
                severity="warning",
                message=(
                    f"Source VM '{vm_name}' was not found, so its "
                    "network interfaces could not be evaluated."
                ),
                data={
                    "vm_name": vm_name,
                    "resource_group_name": resource_group_name,
                    "vm_exists": False,
                },
            )

            self.log_complete()
            return tool_result

        vm_data = vm_result.get("data") or {}
        vm_properties = vm_data.get("properties") or {}

        actual_source_location = self._normalize_location(
            vm_data.get("location", "")
        )

        location_matches = (
            not expected_source_location
            or actual_source_location
            == expected_source_location
        )

        network_profile = (
            vm_properties.get("networkProfile") or {}
        )

        nic_references = (
            network_profile.get("networkInterfaces") or []
        )

        if not nic_references:
            tool_result = ToolResult(
                tool_name=self.name,
                status="validation_failed",
                severity="warning",
                message=(
                    f"Source VM '{vm_name}' does not contain any "
                    "network-interface references."
                ),
                data={
                    "vm_name": vm_name,
                    "resource_group_name": resource_group_name,
                    "vm_exists": True,
                    "nic_count": 0,
                    "network_mapping_ready": False,
                },
            )

            self.log_complete()
            return tool_result

        nic_results: list[dict[str, Any]] = []
        missing_nics: list[str] = []

        for index, nic_reference in enumerate(nic_references):
            nic_id = nic_reference.get("id") or ""
            nic_reference_properties = (
                nic_reference.get("properties") or {}
            )

            vm_reference_primary = (
                nic_reference_properties.get(
                    "primary",
                    index == 0,
                )
            )

            if not nic_id:
                missing_nics.append(
                    f"NIC reference at index {index}"
                )
                continue

            nic_data = self._get_nic(nic_id)

            if nic_data is None:
                missing_nics.append(nic_id)
                continue

            nic_properties = nic_data.get("properties") or {}
            nic_resource_details = self._parse_resource_id(
                nic_id
            )

            ip_configurations = [
                self._build_ip_configuration(ip_config)
                for ip_config in (
                    nic_properties.get("ipConfigurations") or []
                )
            ]

            primary_ip_configurations = [
                ip_config
                for ip_config in ip_configurations
                if ip_config["primary"]
            ]

            if (
                not primary_ip_configurations
                and ip_configurations
            ):
                primary_ip_configurations = [
                    ip_configurations[0]
                ]

            nsg_reference = (
                nic_properties.get("networkSecurityGroup")
                or {}
            )

            nic_results.append(
                {
                    "nic_name": nic_data.get("name"),
                    "nic_resource_group": (
                        nic_resource_details.get(
                            "resource_group_name"
                        )
                    ),
                    "nic_resource_id": nic_id,
                    "primary_nic": bool(
                        vm_reference_primary
                    ),
                    "location": self._normalize_location(
                        nic_data.get("location", "")
                    ),
                    "provisioning_state": (
                        nic_properties.get(
                            "provisioningState"
                        )
                    ),
                    "enable_accelerated_networking": (
                        nic_properties.get(
                            "enableAcceleratedNetworking"
                        )
                    ),
                    "enable_ip_forwarding": (
                        nic_properties.get(
                            "enableIPForwarding"
                        )
                    ),
                    "mac_address": nic_properties.get(
                        "macAddress"
                    ),
                    "nsg_id": nsg_reference.get("id"),
                    "nsg_attached": bool(
                        nsg_reference.get("id")
                    ),
                    "ip_configuration_count": len(
                        ip_configurations
                    ),
                    "ip_configurations": ip_configurations,
                    "primary_ip_configurations": (
                        primary_ip_configurations
                    ),
                    "dns_servers": (
                        nic_properties
                        .get("dnsSettings", {})
                        .get("dnsServers", [])
                    ),
                    "applied_dns_servers": (
                        nic_properties
                        .get("dnsSettings", {})
                        .get("appliedDnsServers", [])
                    ),
                }
            )

        primary_nics = [
            nic
            for nic in nic_results
            if nic["primary_nic"]
        ]

        if not primary_nics and nic_results:
            nic_results[0]["primary_nic"] = True
            primary_nics = [nic_results[0]]

        source_subnets = []

        for nic in nic_results:
            for ip_config in nic["ip_configurations"]:
                if ip_config["subnet_id"]:
                    source_subnets.append(
                        {
                            "nic_name": nic["nic_name"],
                            "primary_nic": nic["primary_nic"],
                            "ip_configuration_name": (
                                ip_config["name"]
                            ),
                            "private_ip_address": (
                                ip_config[
                                    "private_ip_address"
                                ]
                            ),
                            "source_vnet_resource_group": (
                                ip_config[
                                    "source_vnet_resource_group"
                                ]
                            ),
                            "source_vnet_name": (
                                ip_config["source_vnet_name"]
                            ),
                            "source_subnet_name": (
                                ip_config[
                                    "source_subnet_name"
                                ]
                            ),
                            "source_subnet_id": (
                                ip_config["subnet_id"]
                            ),
                        }
                    )

        mapping_recommendations = []

        for source_subnet in source_subnets:
            mapping_recommendations.append(
                {
                    "nic_name": source_subnet["nic_name"],
                    "primary_nic": (
                        source_subnet["primary_nic"]
                    ),
                    "source_vnet_resource_group": (
                        source_subnet[
                            "source_vnet_resource_group"
                        ]
                    ),
                    "source_vnet_name": (
                        source_subnet["source_vnet_name"]
                    ),
                    "source_subnet_name": (
                        source_subnet["source_subnet_name"]
                    ),
                    "target_resource_group": (
                        target_resource_group or None
                    ),
                    "target_vnet_name": (
                        target_vnet or None
                    ),
                    "target_subnet_name": (
                        target_subnet or None
                    ),
                    "mapping_complete": bool(
                        target_resource_group
                        and target_vnet
                        and target_subnet
                    ),
                }
            )

        blocking_findings = []
        warning_findings = []

        if not location_matches:
            blocking_findings.append(
                "VM location does not match the supplied source region."
            )

        if missing_nics:
            blocking_findings.append(
                "One or more referenced NICs could not be retrieved."
            )

        if not nic_results:
            blocking_findings.append(
                "No attached NIC resources were successfully retrieved."
            )

        if len(primary_nics) != 1:
            warning_findings.append(
                "The VM does not have exactly one identifiable primary NIC."
            )

        if not source_subnets:
            blocking_findings.append(
                "No source subnet references were found."
            )

        nic_location_mismatches = [
            nic["nic_name"]
            for nic in nic_results
            if (
                nic["location"]
                and nic["location"] != actual_source_location
            )
        ]

        if nic_location_mismatches:
            warning_findings.append(
                "One or more NIC locations differ from the VM location."
            )

        if any(
            nic["enable_ip_forwarding"]
            for nic in nic_results
        ):
            warning_findings.append(
                "IP forwarding is enabled on one or more NICs."
            )

        if not (
            target_resource_group
            and target_vnet
            and target_subnet
        ):
            warning_findings.append(
                "Target network mapping is incomplete."
            )

        network_mapping_ready = (
            not blocking_findings
            and bool(source_subnets)
            and bool(
                target_resource_group
                and target_vnet
                and target_subnet
            )
        )

        if blocking_findings:
            status = "validation_failed"
            severity = "warning"
            message = (
                f"Source VM '{vm_name}' network discovery "
                "completed with blocking findings."
            )

        elif warning_findings:
            status = "validation_failed"
            severity = "warning"
            message = (
                f"Source VM '{vm_name}' network discovery "
                "completed, but the mapping requires review."
            )

        else:
            status = "success"
            severity = "info"
            message = (
                f"Source VM '{vm_name}' network interfaces were "
                "discovered and the target mapping is ready."
            )

        tool_result = ToolResult(
            tool_name=self.name,
            status=status,
            severity=severity,
            message=message,
            data={
                "vm_name": vm_name,
                "resource_group_name": resource_group_name,
                "vm_exists": True,
                "vm_location": actual_source_location,
                "expected_source_location": (
                    expected_source_location or None
                ),
                "location_matches": location_matches,
                "nic_count": len(nic_results),
                "primary_nic_count": len(primary_nics),
                "primary_nic_names": [
                    nic["nic_name"]
                    for nic in primary_nics
                ],
                "network_interfaces": nic_results,
                "source_subnets": source_subnets,
                "missing_nic_references": missing_nics,
                "target_resource_group": (
                    target_resource_group or None
                ),
                "target_vnet": target_vnet or None,
                "target_subnet": target_subnet or None,
                "mapping_recommendations": (
                    mapping_recommendations
                ),
                "network_mapping_ready": (
                    network_mapping_ready
                ),
                "blocking_findings": blocking_findings,
                "warning_findings": warning_findings,
                "validation_scope": (
                    "Discovers VM NIC and IP-configuration metadata "
                    "and prepares a proposed source-to-target mapping. "
                    "It does not create the Azure Site Recovery network "
                    "mapping or modify NIC settings."
                ),
            },
        )

        self.log_complete()
        return tool_result