import os
import httpx
from .base import Agent


class TempAgent(Agent):
    """OpenRouter agent. Rotating external model for diversity testing."""

    name = "TempAgent"
    model = "mistralai/mistral-7b-instruct"

    def __init__(self, model: str = "mistralai/mistral-7b-instruct", timeout: float = 30):
        self.model = model
        self.timeout = timeout

    @property
    def api_key(self) -> str | None:
        return os.getenv("OPENROUTER_API_KEY")

    async def fetch(self, prompt: str) -> str:
        if not self.api_key:
            print(f"[{self.name} Error] OPENROUTER_API_KEY is not set.")
            return f"[{self.name}] API Key Missing"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=self.timeout,
                )
                res.raise_for_status()
                return res.json()["choices"][0]["message"]["content"]
            except httpx.HTTPStatusError as e:
                print(f"[{self.name} HTTPStatusError] {e.response.status_code}: {e.response.text}")
                return f"[{self.name}] HTTP {e.response.status_code}"
            except Exception as e:
                print(f"[{self.name} Error] {type(e).__name__}: {e}")
                return f"[{self.name}] Failed"
