from typing import Any

import requests
from azure.identity import DefaultAzureCredential


class AzureResourceService:
    """Handles authenticated Azure Resource Manager REST API requests."""

    ARM_BASE_URL = "https://management.azure.com"
    ARM_SCOPE = "https://management.azure.com/.default"

    def __init__(self, subscription_id: str):
        if not subscription_id:
            raise ValueError(
                "AZURE_SUBSCRIPTION_ID is missing from the .env file."
            )

        self.subscription_id = subscription_id
        self.credential = DefaultAzureCredential()

    def _get_headers(self) -> dict[str, str]:
        token = self.credential.get_token(self.ARM_SCOPE)

        return {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
        }

    def get(self, path: str, api_version: str) -> dict[str, Any]:
        url = f"{self.ARM_BASE_URL}{path}"

        response = requests.get(
            url,
            headers=self._get_headers(),
            params={"api-version": api_version},
            timeout=30,
        )

        if response.status_code == 404:
            return {
                "found": False,
                "status_code": 404,
                "data": None,
            }

        response.raise_for_status()

        return {
            "found": True,
            "status_code": response.status_code,
            "data": response.json(),
        }