import os
import httpx
from .base import Agent


class Sol(Agent):
    """OpenAI GPT-4o agent."""

    name = "GPT-4o"
    model = "gpt-4o"

    def __init__(self, model: str = "gpt-4o", timeout: float = 30, temperature: float = 0.7):
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
            except httpx.TimeoutException:
                print(f"[{self.name} Timeout] Request timed out after {self.timeout}s.")
                return f"[{self.name}] Timeout"
            except httpx.ConnectError as e:
                print(f"[{self.name} ConnectError] Could not reach OpenAI API: {e}")
                return f"[{self.name}] Connection failed"
            except httpx.HTTPStatusError as e:
                print(f"[{self.name} HTTPStatusError] {e.response.status_code}: {e.response.text}")
                return f"[{self.name}] HTTP {e.response.status_code}"
            except (KeyError, IndexError) as e:
                print(f"[{self.name} ParseError] Unexpected response structure: {e}")
                return f"[{self.name}] Malformed response"
            except Exception as e:
                print(f"[{self.name} Error] {type(e).__name__}: {e}")
                return f"[{self.name}] Failed"
