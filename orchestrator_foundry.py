import os
import asyncio
import httpx
from dotenv import load_dotenv

# Load .env from the same directory as this script
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path)

# === API KEYS from .env ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")  # For Gemini
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

# === Debug Print ===
print("[Debug] .env path:", dotenv_path)

# === Headers for each provider ===
HEADERS = {
    "openai": {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    },
    "anthropic": {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json"
    },
    "google": {
        "Content-Type": "application/json"
    },
    "openrouter": {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
}

# === Agent: Sol (OpenAI GPT-4) ===
async def fetch_sol(prompt: str):
    if not OPENAI_API_KEY:
        print("[Sol Error] OPENAI_API_KEY is not set.")
        return "❌ Sol: API Key Missing"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers=HEADERS["openai"],
                json={
                    "model": "gpt-4",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.7
                },
                timeout=30
            )
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            print(f"[Sol HTTPStatusError] {e.response.status_code}: {e.response.text}")
            return f"❌ Sol failed with HTTP {e.response.status_code}."
        except Exception as e:
            print(f"[Sol Error] {type(e).__name__}: {e}")
            return "❌ Sol failed."

# === Agent: Aria (Claude) ===
async def fetch_aria(prompt: str):
    if not ANTHROPIC_API_KEY:
        print("[Aria Error] ANTHROPIC_API_KEY is not set.")
        return "❌ Aria: API Key Missing"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=HEADERS["anthropic"],
                json={
                    "model": "claude-3-opus-20240229",
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=45
            )
            res.raise_for_status()
            return res.json()["content"][0]["text"]
        except httpx.HTTPStatusError as e:
            print(f"[Aria HTTPStatusError] {e.response.status_code}: {e.response.text}")
            return f"❌ Aria failed with HTTP {e.response.status_code}."
        except Exception as e:
            print(f"[Aria Error] {type(e).__name__}: {e}")
            return "❌ Aria failed."

# === Agent: Prism (Gemini) ===
async def fetch_prism(prompt: str):
    if not GOOGLE_API_KEY:
        print("[Prism Error] GOOGLE_API_KEY is not set or empty.")
        return "❌ Prism: API Key Missing"

    model_name = "models/gemini-1.5-pro-latest"
    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
        ]
    }

    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                url,
                headers=HEADERS["google"],
                json=payload,
                timeout=60
            )
            res.raise_for_status()
            data = res.json()

            if "candidates" in data and data["candidates"]:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            elif "promptFeedback" in data:
                feedback = data.get("promptFeedback", {})
                block_reason = feedback.get("blockReason", "Not specified")
                safety_ratings_str = ", ".join(
                    f"{r.get('category')}: {r.get('probability')}" for r in feedback.get("safetyRatings", [])
                )
                print(f"[Prism Warning] Content filtered: {block_reason}. Ratings: [{safety_ratings_str}]")
                return f"❌ Prism: Content filtered ({block_reason})"
            else:
                print(f"[Prism Error] Malformed response: {data}")
                return "❌ Prism: Malformed response"
        except httpx.HTTPStatusError as e:
            print(f"[Prism HTTPStatusError] {e.response.status_code}: {e.response.text}")
            return f"❌ Prism failed with HTTP {e.response.status_code}"
        except Exception as e:
            response_text = getattr(locals().get("res", None), "text", "No response available.")
            print(f"[Prism Error] {type(e).__name__}: {e}")
            print(f"[Prism Raw Response] {response_text}")
            return "❌ Prism failed (exception)"

# === Agent: TempAgent (Mistral via OpenRouter) ===
async def fetch_temp(prompt: str):
    if not OPENROUTER_API_KEY:
        print("[TempAgent Error] OPENROUTER_API_KEY is not set.")
        return "❌ TempAgent: API Key Missing"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=HEADERS["openrouter"],
                json={
                    "model": "mistralai/mistral-7b-instruct",
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=30
            )
            res.raise_for_status()
            return res.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            print(f"[TempAgent HTTPStatusError] {e.response.status_code}: {e.response.text}")
            return f"❌ TempAgent failed with HTTP {e.response.status_code}."
        except Exception as e:
            print(f"[TempAgent Error] {type(e).__name__}: {e}")
            return "❌ TempAgent failed."

# === Orchestration Runner ===
async def run_orchestration(prompt: str) -> dict:
    try:
        print(f"[Orchestrator] Prompt received: {prompt}")
        results = await asyncio.gather(
            fetch_sol(prompt),
            fetch_aria(prompt),
            fetch_prism(prompt),
            fetch_temp(prompt)
        )
        print("[Orchestrator] All results received.")

        responses = {
            "Sol": results[0],
            "Aria": results[1],
            "Prism": results[2],
            "TempAgent": results[3]
        }

        successful_responses = {k: v for k, v in responses.items() if not v.startswith("❌")}
        quorum = {
            "consensus": "🧠 Consensus logic pending...",
            "successful_votes": len(successful_responses),
            "total_agents": len(responses)
        }

        return {
            "responses": responses,
            "quorum": quorum
        }

    except Exception as e:
        print(f"[ERROR] Orchestration Exception: {type(e).__name__} - {e}")
        return {
            "responses": {
                "Sol": "❌ Orchestration Error", "Aria": "❌ Orchestration Error",
                "Prism": "❌ Orchestration Error", "TempAgent": "❌ Orchestration Error"
            },
            "quorum": {"consensus": "❌ Orchestration Failed", "successful_votes": 0, "total_agents": 4}
        }

# === API Key Validation ===
def validate_keys() -> bool:
    missing = []
    if not OPENAI_API_KEY: missing.append("OPENAI")
    if not ANTHROPIC_API_KEY: missing.append("ANTHROPIC")
    if not GOOGLE_API_KEY: missing.append("GOOGLE")
    if not OPENROUTER_API_KEY: missing.append("OPENROUTER")
    if missing:
        print(f"[Startup Error] Missing API keys: {', '.join(missing)}")
        return False
    return True

# === Main Execution ===
async def main():
    prompt = "explain why taco bell rightly became the only restaurant in demolition man"
    result = await run_orchestration(prompt)

    print("\n--- Orchestration Results ---")
    for agent, response in result["responses"].items():
        print(f"Agent: {agent}\nResponse: {response}\n{'-' * 20}")
    print(f"Quorum: {result['quorum']}")

if __name__ == "__main__":
    if validate_keys():
        asyncio.run(main())
    else:
        print("❌ One or more API keys missing. Check your .env file.")
