from abc import ABC, abstractmethod
from datetime import datetime, timezone


class Agent(ABC):
    """Base class for all Maestro agents.

    Every agent has a name, a backing model, and a single async method
    that takes a prompt and returns a response string.
    """

    name: str
    model: str

    @staticmethod
    def build_system_prompt() -> str:
        """Return a system prompt that grounds the model with the current date."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return (
            f"Today's date is {today}. You are a knowledgeable assistant. "
            "Provide direct, current answers. Do not hedge with phrases like "
            "\"as of my last update\" or \"as of my knowledge cutoff\". "
            "If you are uncertain about very recent events, say so briefly "
            "rather than citing a training cutoff date."
        )

    @abstractmethod
    async def fetch(self, prompt: str) -> str:
        """Send a prompt to the backing model and return its response."""
