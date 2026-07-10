from openai import OpenAI
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from config import AppConfig

class AzureAIClient:
    def __init__(self, config: AppConfig):
        token_provider = get_bearer_token_provider(
            DefaultAzureCredential(),
            "https://ai.azure.com/.default"
        )

        self.client = OpenAI(
            base_url=config.azure_ai_base_url,
            api_key=token_provider
        )

        self.model = config.azure_ai_model

    def ask(self, prompt: str) -> str:
        response = self.client.responses.create(
            model=self.model,
            input=prompt
        )

        return response.output_text