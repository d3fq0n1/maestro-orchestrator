import os
import httpx
from .base import Agent


class Aria(Agent):
    """Anthropic Claude Sonnet 4.6 agent."""

    name = "Claude Sonnet 4.6"
    model = "claude-sonnet-4-6"

    def __init__(self, model: str = "claude-sonnet-4-6", timeout: float = 45, max_tokens: int = 2048):
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens

    @property
    def api_key(self) -> str | None:
        return os.getenv("ANTHROPIC_API_KEY")

    async def fetch(self, prompt: str) -> str:
        if not self.api_key:
            print(f"[{self.name} Error] ANTHROPIC_API_KEY is not set.")
            return f"[{self.name}] API Key Missing"

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers=headers,
                    json={
                        "model": self.model,
                        "max_tokens": self.max_tokens,
                        "messages": [{"role": "user", "content": prompt}],
                    },
                    timeout=self.timeout,
                )
                res.raise_for_status()
                return res.json()["content"][0]["text"]
            except httpx.TimeoutException:
                print(f"[{self.name} Timeout] Request timed out after {self.timeout}s.")
                return f"[{self.name}] Timeout"
            except httpx.ConnectError as e:
                print(f"[{self.name} ConnectError] Could not reach Anthropic API: {e}")
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
