import json

import requests

from config import load_config
from core.tool_registry import ToolRegistry
from services.azure_resource_service import AzureResourceService
from tools.recovery_services_vault_tool import (
    RecoveryServicesVaultTool,
)
from tools.resource_group_tool import ResourceGroupTool


def display_result(result) -> None:
    print("\nTool result:")
    print(json.dumps(result.to_dict(), indent=2))


def main() -> None:
    config = load_config()

    azure_service = AzureResourceService(
        subscription_id=config.azure_subscription_id
    )

    registry = ToolRegistry()

    registry.register(ResourceGroupTool(azure_service))
    registry.register(RecoveryServicesVaultTool(azure_service))

    print("=" * 60)
    print("Azure Site Recovery AI Orchestrator")
    print("=" * 60)

    print("\nAvailable tools:")

    for tool in registry.list_tools():
        print(f"- {tool['name']}: {tool['description']}")

    print("\nSelect a precheck:")
    print("1. Check resource group")
    print("2. Check Recovery Services vault")

    selection = input("\nEnter 1 or 2: ").strip()

    try:
        if selection == "1":
            resource_group_name = input(
                "Enter the resource group name: "
            ).strip()

            result = registry.execute(
                "check_resource_group",
                resource_group_name=resource_group_name,
            )

            display_result(result)

        elif selection == "2":
            resource_group_name = input(
                "Enter the vault resource group name: "
            ).strip()

            vault_name = input(
                "Enter the Recovery Services vault name: "
            ).strip()

            expected_location = input(
                "Enter the expected vault location "
                "(example: eastus): "
            ).strip()

            result = registry.execute(
                "check_recovery_services_vault",
                resource_group_name=resource_group_name,
                vault_name=vault_name,
                expected_location=expected_location,
            )

            display_result(result)

        else:
            print("\nInvalid selection. Enter either 1 or 2.")

    except requests.HTTPError as error:
        print(f"\nAzure request failed: {error}")

    except Exception as error:
        print(f"\nApplication error: {error}")


if __name__ == "__main__":
    main()