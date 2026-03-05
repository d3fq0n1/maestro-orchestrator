import os
import httpx
from .base import Agent


class TempAgent(Agent):
    """OpenRouter Llama 3.3 70B agent."""

    name = "Llama 3.3 70B"
    model = "meta-llama/llama-3.3-70b-instruct"

    def __init__(self, model: str = "meta-llama/llama-3.3-70b-instruct", timeout: float = 30):
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
                        "messages": [
                            {"role": "system", "content": self.build_system_prompt()},
                            {"role": "user", "content": prompt},
                        ],
                    },
                    timeout=self.timeout,
                )
                res.raise_for_status()
                return res.json()["choices"][0]["message"]["content"]
            except httpx.TimeoutException:
                print(f"[{self.name} Timeout] Request timed out after {self.timeout}s.")
                return f"[{self.name}] Timeout"
            except httpx.ConnectError as e:
                print(f"[{self.name} ConnectError] Could not reach OpenRouter API: {e}")
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
