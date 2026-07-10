from abc import ABC, abstractmethod
from datetime import datetime


class BaseTool(ABC):
    """
    Base class for every Azure tool.

    Every tool inherits this class.
    """

    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description

    @abstractmethod
    def execute(self, **kwargs):
        """
        Every tool must implement execute().
        """
        pass

    def log_start(self):
        print(
            f"[{datetime.now()}] Starting tool: {self.name}"
        )

    def log_complete(self):
        print(
            f"[{datetime.now()}] Finished tool: {self.name}"
        )