from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class ASRRequest:
    """Structured information extracted from a user's ASR request."""

    vm_name: str = ""
    source_resource_group: str = ""
    source_region: str = ""
    target_region: str = ""
    vault_name: str = ""
    vault_resource_group: str = ""
    target_resource_group: str = ""
    target_vnet: str = ""
    target_subnet: str = ""
    cache_storage_account: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def missing_fields(self) -> list[str]:
        required_fields = {
            "vm_name": self.vm_name,
            "source_resource_group": self.source_resource_group,
            "source_region": self.source_region,
            "target_region": self.target_region,
        }

        return [
            field_name
            for field_name, value in required_fields.items()
            if not value.strip()
        ]