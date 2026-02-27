import os
import httpx
from .base import Agent


class Sol(Agent):
    """OpenAI GPT-4 agent. Primary reasoning engine."""

    name = "Sol"
    model = "gpt-4"

    def __init__(self, model: str = "gpt-4", timeout: float = 30, temperature: float = 0.7):
        self.model = model
        self.timeout = timeout
        self.temperature = temperature

    @property
    def api_key(self) -> str | None:
        return os.getenv("OPENAI_API_KEY")

    async def fetch(self, prompt: str) -> str:
        if not self.api_key:
            print(f"[{self.name} Error] OPENAI_API_KEY is not set.")
            return f"[{self.name}] API Key Missing"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": self.temperature,
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
