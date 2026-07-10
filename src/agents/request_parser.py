import json
import re

from ai_client import AzureAIClient
from models.asr_request import ASRRequest


class ASRRequestParser:
    """Uses GPT-5 to extract ASR details from natural language."""

    def __init__(self, ai_client: AzureAIClient):
        self.ai_client = ai_client

    def parse(self, user_request: str) -> ASRRequest:
        prompt = f"""
You extract Azure Site Recovery request details.

Return only valid JSON.
Do not include Markdown, commentary, or code fences.

Use this exact JSON structure:

{{
  "vm_name": "",
  "source_resource_group": "",
  "source_region": "",
  "target_region": "",
  "vault_name": "",
  "vault_resource_group": "",
  "target_resource_group": "",
  "target_vnet": "",
  "target_subnet": "",
  "cache_storage_account": ""
}}

Rules:
- Populate only values explicitly stated by the user.
- Never invent Azure resource names.
- Use an empty string for anything missing.
- Preserve Azure resource names exactly as entered.
- Normalize regions to Azure format when obvious.
  Examples:
  "East US" becomes "eastus"
  "Central US" becomes "centralus"

User request:
{user_request}
"""

        response_text = self.ai_client.ask(prompt)
        cleaned_text = self._remove_code_fences(response_text)

        try:
            parsed_data = json.loads(cleaned_text)
        except json.JSONDecodeError as error:
            raise ValueError(
                "GPT-5 did not return valid JSON. "
                f"Returned value: {response_text}"
            ) from error

        return ASRRequest(
            vm_name=str(parsed_data.get("vm_name", "")),
            source_resource_group=str(
                parsed_data.get("source_resource_group", "")
            ),
            source_region=str(parsed_data.get("source_region", "")),
            target_region=str(parsed_data.get("target_region", "")),
            vault_name=str(parsed_data.get("vault_name", "")),
            vault_resource_group=str(
                parsed_data.get("vault_resource_group", "")
            ),
            target_resource_group=str(
                parsed_data.get("target_resource_group", "")
            ),
            target_vnet=str(parsed_data.get("target_vnet", "")),
            target_subnet=str(parsed_data.get("target_subnet", "")),
            cache_storage_account=str(
                parsed_data.get("cache_storage_account", "")
            ),
        )

    @staticmethod
    def _remove_code_fences(value: str) -> str:
        cleaned = value.strip()

        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

        return cleaned.strip()