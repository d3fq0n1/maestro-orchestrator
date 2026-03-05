import os
import httpx
from .base import Agent


class Prism(Agent):
    """Google Gemini 2.5 Flash agent."""

    name = "Gemini 2.5 Flash"
    model = "models/gemini-2.5-flash"

    SAFETY_SETTINGS = [
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    ]

    def __init__(self, model: str = "models/gemini-2.5-flash", timeout: float = 60):
        self.model = model
        self.timeout = timeout

    @property
    def api_key(self) -> str | None:
        return os.getenv("GOOGLE_API_KEY")

    async def fetch(self, prompt: str) -> str:
        if not self.api_key:
            print(f"[{self.name} Error] GOOGLE_API_KEY is not set.")
            return f"[{self.name}] API Key Missing"

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "safetySettings": self.SAFETY_SETTINGS,
        }

        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=self.timeout,
                )
                res.raise_for_status()
                data = res.json()

                if "candidates" in data and data["candidates"]:
                    return data["candidates"][0]["content"]["parts"][0]["text"]

                if "promptFeedback" in data:
                    feedback = data["promptFeedback"]
                    block_reason = feedback.get("blockReason", "Not specified")
                    ratings = ", ".join(
                        f"{r.get('category')}: {r.get('probability')}"
                        for r in feedback.get("safetyRatings", [])
                    )
                    print(f"[{self.name} Warning] Content filtered: {block_reason}. Ratings: [{ratings}]")
                    return f"[{self.name}] Content filtered ({block_reason})"

                print(f"[{self.name} Error] Malformed response: {data}")
                return f"[{self.name}] Malformed response"

            except httpx.TimeoutException:
                print(f"[{self.name} Timeout] Request timed out after {self.timeout}s.")
                return f"[{self.name}] Timeout"
            except httpx.ConnectError as e:
                print(f"[{self.name} ConnectError] Could not reach Google API: {e}")
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
