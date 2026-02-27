from .base import Agent


class MockAgent(Agent):
    """Mock agent for testing and offline development."""

    def __init__(self, name: str = "MockAgent", model: str = "mock-v1", response_style: str = "neutral"):
        self.name = name
        self.model = model
        self.response_style = response_style

    async def fetch(self, prompt: str) -> str:
        styles = {
            "neutral": f"[{self.name}] Analyzing '{prompt}' from a balanced perspective.",
            "empathic": f"[{self.name}] In my view, the key to '{prompt}' is empathy and systems thinking.",
            "historical": f"[{self.name}] Historically, questions like '{prompt}' have driven scientific revolution.",
        }
        return styles.get(self.response_style, styles["neutral"])
