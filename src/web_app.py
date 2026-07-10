import json

import requests
import streamlit as st

from ai_client import AzureAIClient
from config import load_config
from core.tool_registry import ToolRegistry
from services.azure_resource_service import AzureResourceService
from tools.recovery_services_vault_tool import RecoveryServicesVaultTool
from tools.resource_group_tool import ResourceGroupTool


def build_registry(config) -> ToolRegistry:
    """Create and populate the orchestrator tool registry."""

    azure_service = AzureResourceService(
        subscription_id=config.azure_subscription_id
    )

    registry = ToolRegistry()
    registry.register(ResourceGroupTool(azure_service))
    registry.register(RecoveryServicesVaultTool(azure_service))

    return registry


def initialize_session_state() -> None:
    """Create the initial web application state."""

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {
                "role": "assistant",
                "content": (
                    "Azure Site Recovery AI Orchestrator is online. "
                    "Describe the Azure Site Recovery task you want to perform."
                ),
            }
        ]

    if "pending_action" not in st.session_state:
        st.session_state.pending_action = None


def display_tool_result(result) -> None:
    """Display a tool result in a readable format."""

    result_data = result.to_dict()

    status = result_data["status"]

    if status == "success":
        st.success(result_data["message"])
    elif status == "not_found":
        st.warning(result_data["message"])
    elif status == "validation_failed":
        st.warning(result_data["message"])
    else:
        st.error(result_data["message"])

    with st.expander("View technical details"):
        st.json(result_data)


def run_resource_group_check(registry: ToolRegistry) -> None:
    """Display and execute the resource-group precheck form."""

    st.subheader("Resource Group Precheck")

    resource_group_name = st.text_input(
        "Resource group name",
        placeholder="rg-asr-ai-dev-eastus",
        key="resource_group_name",
    )

    if st.button(
        "Run Resource Group Check",
        type="primary",
        use_container_width=True,
    ):
        if not resource_group_name.strip():
            st.error("Enter a resource group name.")
            return

        try:
            with st.status(
                "Checking Azure Resource Manager...",
                expanded=True,
            ) as status:
                st.write("Authenticating with Microsoft Entra ID")
                st.write(
                    f"Checking resource group: {resource_group_name}"
                )

                result = registry.execute(
                    "check_resource_group",
                    resource_group_name=resource_group_name.strip(),
                )

                status.update(
                    label="Resource group check complete",
                    state="complete",
                    expanded=False,
                )

            display_tool_result(result)

        except requests.HTTPError as error:
            st.error(f"Azure request failed: {error}")
        except Exception as error:
            st.error(f"Application error: {error}")


def run_vault_check(registry: ToolRegistry) -> None:
    """Display and execute the Recovery Services vault form."""

    st.subheader("Recovery Services Vault Precheck")

    vault_resource_group = st.text_input(
        "Vault resource group",
        placeholder="rg-asr-dr-centralus",
        key="vault_resource_group",
    )

    vault_name = st.text_input(
        "Recovery Services vault name",
        placeholder="rsv-asr-centralus-dev",
        key="vault_name",
    )

    expected_location = st.text_input(
        "Expected vault location",
        placeholder="centralus",
        key="expected_location",
    )

    if st.button(
        "Run Vault Check",
        type="primary",
        use_container_width=True,
    ):
        if not vault_resource_group.strip():
            st.error("Enter the vault resource group.")
            return

        if not vault_name.strip():
            st.error("Enter the Recovery Services vault name.")
            return

        try:
            with st.status(
                "Checking Recovery Services vault...",
                expanded=True,
            ) as status:
                st.write("Authenticating with Microsoft Entra ID")
                st.write(f"Checking vault: {vault_name}")

                result = registry.execute(
                    "check_recovery_services_vault",
                    resource_group_name=vault_resource_group.strip(),
                    vault_name=vault_name.strip(),
                    expected_location=expected_location.strip(),
                )

                status.update(
                    label="Vault check complete",
                    state="complete",
                    expanded=False,
                )

            display_tool_result(result)

        except requests.HTTPError as error:
            st.error(f"Azure request failed: {error}")
        except Exception as error:
            st.error(f"Application error: {error}")


def run_ai_chat(ai_client: AzureAIClient) -> None:
    """Display the first conversational AI interface."""

    st.subheader("AI Planning Assistant")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_request = st.chat_input(
        "Example: Replicate FinanceVM01 from East US to Central US"
    )

    if not user_request:
        return

    st.session_state.messages.append(
        {
            "role": "user",
            "content": user_request,
        }
    )

    with st.chat_message("user"):
        st.markdown(user_request)

    planning_prompt = f"""
You are the planning assistant for an Azure Site Recovery orchestrator.

Create a concise read-only precheck plan for the user's request.

Do not claim that checks have already been completed.
Do not create, change, delete, or replicate any Azure resources.
Clearly separate:
1. Understood request
2. Required missing information
3. Read-only prechecks
4. Changes that would require explicit approval

User request:
{user_request}
"""

    try:
        with st.chat_message("assistant"):
            with st.spinner("Creating the ASR precheck plan..."):
                response = ai_client.ask(planning_prompt)

            st.markdown(response)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": response,
            }
        )

    except Exception as error:
        error_message = f"AI request failed: {error}"

        with st.chat_message("assistant"):
            st.error(error_message)

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": error_message,
            }
        )


def main() -> None:
    st.set_page_config(
        page_title="ASR AI Orchestrator",
        page_icon="🛡️",
        layout="wide",
    )

    initialize_session_state()

    config = load_config()
    registry = build_registry(config)
    ai_client = AzureAIClient(config)

    st.title("🛡️ Azure Site Recovery AI Orchestrator")
    st.caption(
        "AI-assisted planning and read-only Azure Site Recovery prechecks"
    )

    with st.sidebar:
        st.header("Environment")

        st.write("**Authentication:** Microsoft Entra ID")
        st.write(f"**AI model:** `{config.azure_ai_model}`")

        masked_subscription = (
            f"{config.azure_subscription_id[:8]}..."
            if config.azure_subscription_id
            else "Not configured"
        )

        st.write(f"**Subscription:** `{masked_subscription}`")

        st.divider()

        st.header("Safety Mode")
        st.success("Read-only prechecks enabled")
        st.warning("Resource creation is disabled")

        if st.button("Clear Conversation"):
            st.session_state.messages = []
            st.session_state.pending_action = None
            st.rerun()

    chat_tab, resource_group_tab, vault_tab = st.tabs(
        [
            "AI Assistant",
            "Resource Group",
            "Recovery Services Vault",
        ]
    )

    with chat_tab:
        run_ai_chat(ai_client)

    with resource_group_tab:
        run_resource_group_check(registry)

    with vault_tab:
        run_vault_check(registry)


if __name__ == "__main__":
    main()