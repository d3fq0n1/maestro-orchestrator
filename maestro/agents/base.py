from abc import ABC, abstractmethod


class Agent(ABC):
    """Base class for all Maestro agents.

    Every agent has a name, a backing model, and a single async method
    that takes a prompt and returns a response string.
    """

    name: str
    model: str

    @abstractmethod
    async def fetch(self, prompt: str) -> str:
        """Send a prompt to the backing model and return its response."""
