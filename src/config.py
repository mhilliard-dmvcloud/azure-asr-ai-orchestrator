import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class AppConfig:
    azure_ai_base_url: str
    azure_ai_model: str
    azure_subscription_id: str

def load_config() -> AppConfig:
    return AppConfig(
        azure_ai_base_url=os.getenv("AZURE_AI_BASE_URL", ""),
        azure_ai_model=os.getenv("AZURE_AI_MODEL", "gpt-5"),
        azure_subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID", ""),
    )