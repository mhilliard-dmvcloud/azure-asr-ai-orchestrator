import json

import requests
import streamlit as st


from agents.request_parser import ASRRequestParser
from ai_client import AzureAIClient
from config import load_config
from core.execution_engine import ExecutionEngine
from core.execution_plan_builder import ExecutionPlanBuilder
from core.tool_registry import ToolRegistry
from models.asr_request import ASRRequest
from services.azure_resource_service import AzureResourceService
from tools.recovery_services_vault_tool import RecoveryServicesVaultTool
from tools.resource_group_tool import ResourceGroupTool
from tools.cache_storage_account_tool import (
    CacheStorageAccountTool,
)
from tools.target_subnet_tool import TargetSubnetTool
from tools.target_virtual_network_tool import (
    TargetVirtualNetworkTool,
)
from tools.target_nsg_rule_tool import TargetNsgRuleTool
from tools.source_vm_eligibility_tool import (
    SourceVmEligibilityTool,
)

def build_registry(config) -> ToolRegistry:
    """Create and populate the orchestrator tool registry."""

    azure_service = AzureResourceService(
        subscription_id=config.azure_subscription_id
    )

    registry = ToolRegistry()
    registry.register(ResourceGroupTool(azure_service))
    registry.register(
    SourceVmEligibilityTool(azure_service)
    )
    registry.register(CacheStorageAccountTool(azure_service))
    registry.register(
        TargetVirtualNetworkTool(azure_service)
    )
    registry.register(
        TargetSubnetTool(azure_service)
    )
    registry.register(
        TargetNsgRuleTool(azure_service)
    )
    registry.register(RecoveryServicesVaultTool(azure_service)
)
    

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

    if "asr_request" not in st.session_state:
        st.session_state.asr_request = None

    if "request_parsed" not in st.session_state:
        st.session_state.request_parsed = False

    if "execution_plan" not in st.session_state:
        st.session_state.execution_plan = None    


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

def display_execution_timeline(plan) -> None:
    """Display the current execution-plan status."""

    st.subheader("Execution Timeline")

    for step in plan.steps:
        if step.status == "completed":
            icon = "✅"
        elif step.status == "warning":
            icon = "⚠️"
        elif step.status == "failed":
            icon = "❌"
        elif step.status == "running":
            icon = "⏳"
        else:
            icon = "⬜"

        st.markdown(
            f"{icon} **{step.name}** — `{step.status}`"
        )

        if step.error:
            st.error(step.error)

        if step.result:
            with st.expander(
                f"View result: {step.name}",
                expanded=False,
            ):
                st.json(step.result)


def display_asr_request_review(
    registry: ToolRegistry,
) -> None:
    """Allow the user to review and approve extracted ASR details."""

    request_data = st.session_state.asr_request

    if request_data is None:
        return

    st.divider()
    st.subheader("Review ASR Request")

    st.info(
        "Review and correct the information below. "
        "No Azure changes will be made."
    )

    with st.form("asr_request_review_form"):
        vm_name = st.text_input(
            "VM name",
            value=request_data.vm_name,
        )

        source_resource_group = st.text_input(
            "Source resource group",
            value=request_data.source_resource_group,
        )

        source_region = st.text_input(
            "Source region",
            value=request_data.source_region,
            placeholder="eastus",
        )

        target_region = st.text_input(
            "Target region",
            value=request_data.target_region,
            placeholder="centralus",
        )

        vault_name = st.text_input(
            "Recovery Services vault name",
            value=request_data.vault_name,
        )

        vault_resource_group = st.text_input(
            "Vault resource group",
            value=request_data.vault_resource_group,
        )

        target_resource_group = st.text_input(
            "Target resource group",
            value=request_data.target_resource_group,
        )

        target_vnet = st.text_input(
            "Target virtual network",
            value=request_data.target_vnet,
        )

        target_subnet = st.text_input(
            "Target subnet",
            value=request_data.target_subnet,
        )

        cache_storage_resource_group = st.text_input(
            "Cache storage resource group",
            value=request_data.cache_storage_resource_group,
            placeholder="rg-asr-source-eastus",
        )

        cache_storage_account = st.text_input(
            "Cache storage account",
            value=request_data.cache_storage_account,
            placeholder="stasrcacheeastus001",
        )
    
        approved = st.form_submit_button(
            "Approve Read-Only Prechecks",
            type="primary",
            use_container_width=True,
        )

    if approved:
        updated_request = ASRRequest(
            vm_name=vm_name.strip(),
            source_resource_group=source_resource_group.strip(),
            source_region=source_region.strip(),
            target_region=target_region.strip(),
            vault_name=vault_name.strip(),
            vault_resource_group=vault_resource_group.strip(),
            target_resource_group=target_resource_group.strip(),
            target_vnet=target_vnet.strip(),
            target_subnet=target_subnet.strip(),
            cache_storage_resource_group=(
                cache_storage_resource_group.strip()
           ),
            cache_storage_account=(
                cache_storage_account.strip()
            ),
        )

        st.session_state.asr_request = updated_request

        missing_fields = updated_request.missing_fields()

        if missing_fields:
            st.error(
                "Complete these required fields before running prechecks: "
                + ", ".join(missing_fields)
            )
            return

        st.success("Read-only prechecks approved.")

        plan_builder = ExecutionPlanBuilder()
        execution_engine = ExecutionEngine(registry)

        execution_plan = plan_builder.build_precheck_plan(
            updated_request
        )

        st.subheader("Approved Execution Plan")
        st.write(execution_plan.description)

        for step in execution_plan.steps:
            st.markdown(
                f"- **{step.name}**: {step.description}"
            )

        with st.status(
            "Running approved read-only prechecks...",
            expanded=True,
        ) as status:

            def update_progress(step) -> None:
                st.write(
                    f"{step.name}: {step.status}"
                )

            completed_plan = execution_engine.execute_plan(
                plan=execution_plan,
                progress_callback=update_progress,
            )

            # Preserve the completed timeline across Streamlit reruns.
            st.session_state.execution_plan = completed_plan

            if completed_plan.status == "completed":
                status.update(
                    label="All prechecks completed successfully",
                    state="complete",
                    expanded=False,
                )

            elif (
                completed_plan.status
                == "completed_with_warnings"
            ):
                status.update(
                    label="Prechecks completed with warnings",
                    state="complete",
                    expanded=True,
                )

            else:
                status.update(
                    label="One or more prechecks failed",
                    state="error",
                    expanded=True,
                )

    # Display the latest timeline even after Streamlit reruns.
    if st.session_state.execution_plan is not None:
        display_execution_timeline(
            st.session_state.execution_plan
        )


def run_ai_chat(
    ai_client: AzureAIClient,
    registry: ToolRegistry,
) -> None:
    """Display the conversational ASR intake interface."""

    st.subheader("AI Planning Assistant")

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    user_request = st.chat_input(
        "Example: Replicate FinanceVM01 from East US to Central US"
    )

    if user_request:
        st.session_state.messages.append(
            {
                "role": "user",
                "content": user_request,
            }
        )

        with st.chat_message("user"):
            st.markdown(user_request)

        try:
            parser = ASRRequestParser(ai_client)

            with st.chat_message("assistant"):
                with st.spinner(
                    "Analyzing the Azure Site Recovery request..."
                ):
                    parsed_request = parser.parse(user_request)

                missing_fields = parsed_request.missing_fields()

                response = (
                    "I extracted the ASR request details. "
                    "Review them below before approving any prechecks."
                )

                if missing_fields:
                    response += (
                        "\n\nRequired information is still missing: "
                        + ", ".join(missing_fields)
                    )

                st.markdown(response)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": response,
                }
            )

            st.session_state.asr_request = parsed_request
            st.session_state.request_parsed = True
            st.session_state.execution_plan = None

        except Exception as error:
            error_message = f"Request analysis failed: {error}"

            with st.chat_message("assistant"):
                st.error(error_message)

            st.session_state.messages.append(
                {
                    "role": "assistant",
                    "content": error_message,
                }
            )

    if st.session_state.request_parsed:
        display_asr_request_review(registry)
    


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
            st.session_state.asr_request = None
            st.session_state.request_parsed = False
            st.session_state.execution_plan = None
            st.rerun()

    chat_tab, resource_group_tab, vault_tab = st.tabs(
        [
            "AI Assistant",
            "Resource Group",
            "Recovery Services Vault",
        ]
    )

    with chat_tab:
        run_ai_chat(
            ai_client=ai_client,
            registry=registry,
    )

    with resource_group_tab:
        run_resource_group_check(registry)

    with vault_tab:
        run_vault_check(registry)


if __name__ == "__main__":
    main()