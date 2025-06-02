import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

# === API KEYS from .env ===
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY") # For Gemini
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

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
    "google": { # For Gemini: API key goes in URL, not as Bearer token
        "Content-Type": "application/json"
    },
    "openrouter": {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
}

# === Sol (OpenAI GPT-4 or similar) ===
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
                    "model": "gpt-4", # Or your preferred OpenAI model
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

# === Aria (Anthropic Claude) ===
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
                    "model": "claude-3-opus-20240229", # Or your preferred Claude model
                    "max_tokens": 2048, # Increased max_tokens
                    "messages": [{"role": "user", "content": prompt}]
                },
                timeout=45 # Slightly increased timeout
            )
            res.raise_for_status()
            return res.json()["content"][0]["text"]
        except httpx.HTTPStatusError as e:
            print(f"[Aria HTTPStatusError] {e.response.status_code}: {e.response.text}")
            return f"❌ Aria failed with HTTP {e.response.status_code}."
        except Exception as e:
            print(f"[Aria Error] {type(e).__name__}: {e}")
            return "❌ Aria failed."

# === Prism (Google Gemini) ===
async def fetch_prism(prompt: str):
    if not GOOGLE_API_KEY:
        print("[Prism Error] GOOGLE_API_KEY is not set or empty.")
        return "❌ Prism: API Key Missing"

    # Use a current and generally available model
    model_name = "models/gemini-1.5-pro-latest"

    url = f"https://generativelanguage.googleapis.com/v1beta/{model_name}:generateContent?key={GOOGLE_API_KEY}"

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "safetySettings": [ # Optional: Adjust safety settings if needed
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"}
        ]
    }

    async with httpx.AsyncClient() as client:
        try:
            # print(f"[Prism] Requesting URL (key hidden): {url.split('?')[0]}") # Debug
            res = await client.post(
                url,
                headers=HEADERS["google"],
                json=payload,
                timeout=60 # Gemini can sometimes be slower
            )
            res.raise_for_status()
            data = res.json()

            if "candidates" in data and data["candidates"] and \
               data["candidates"][0].get("content") and \
               data["candidates"][0]["content"].get("parts") and \
               data["candidates"][0]["content"]["parts"][0].get("text") is not None:
                return data["candidates"][0]["content"]["parts"][0]["text"]
            elif "promptFeedback" in data:
                feedback = data.get("promptFeedback", {})
                block_reason = feedback.get("blockReason", "Not specified")
                safety_ratings_str = ", ".join([f"{rating.get('category')}: {rating.get('probability')}" for rating in feedback.get("safetyRatings", [])])
                print(f"[Prism Warning] Content filtered or unavailable. Reason: {block_reason}. Ratings: [{safety_ratings_str}]")
                # print(f"[Gemini Raw Data on Filter] {data}") # For detailed debugging
                return f"❌ Prism: Content filtered ({block_reason})"
            else:
                print(f"[Prism Error] Response missing 'candidates' or expected structure: {data}")
                return "❌ Prism: Malformed response"

        except httpx.HTTPStatusError as e:
            print(f"[Prism HTTPStatusError] {e.response.status_code}: {e.response.text}")
            return f"❌ Prism failed with HTTP {e.response.status_code}"
        except Exception as e:
            response_text = "No response object or text available."
            if 'res' in locals() and hasattr(res, 'text'):
                response_text = res.text
            print(f"[Prism Error on Exception] {type(e).__name__}: {e}")
            print(f"[Gemini Raw on Exception] {response_text}")
            return "❌ Prism failed (exception)"

# === TempAgent (Mistral via OpenRouter) ===
async def fetch_temp(prompt: str): # Definition was missing in the error context, ensuring it's here
    if not OPENROUTER_API_KEY:
        print("[TempAgent Error] OPENROUTER_API_KEY is not set.")
        return "❌ TempAgent: API Key Missing"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=HEADERS["openrouter"],
                json={
                    "model": "mistralai/mistral-7b-instruct", # Or your preferred OpenRouter model
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

# === Run all agents ===
async def run_orchestration(prompt: str) -> dict:
    try:
        print(f"[Orchestrator] Prompt received: {prompt}")

        # Define all tasks
        task_sol = fetch_sol(prompt)
        task_aria = fetch_aria(prompt)
        task_prism = fetch_prism(prompt)
        task_temp = fetch_temp(prompt) # Ensure this function is defined

        # Gather results from all tasks concurrently
        results = await asyncio.gather(
            task_sol,
            task_aria,
            task_prism,
            task_temp
        )
        print("[Orchestrator] All results received.")

        responses = {
            "Sol": results[0],
            "Aria": results[1],
            "Prism": results[2],
            "TempAgent": results[3]
        }

        # Basic quorum logic (can be expanded)
        successful_responses = {k: v for k, v in responses.items() if not v.startswith("❌")}
        quorum = {
            "consensus": "🧠 Consensus logic pending...", # Placeholder for actual consensus logic
            "successful_votes": len(successful_responses),
            "total_agents": len(responses)
        }

        return {
            "responses": responses,
            "quorum": quorum
        }

    except Exception as e: # Catch any unexpected errors during orchestration
        print(f"[ERROR] Unhandled exception during orchestration: {type(e).__name__} - {e}")
        # Fallback response structure in case of major orchestration failure
        return {
            "responses": {
                "Sol": "❌ Orchestration Error", "Aria": "❌ Orchestration Error",
                "Prism": "❌ Orchestration Error", "TempAgent": "❌ Orchestration Error"
            },
            "quorum": {"consensus": "❌ Orchestration Failed", "successful_votes": 0, "total_agents": 4}
        }

# === Example Usage (Uncomment to run this script directly) ===
# async def main():
#     print("--- Sanity Check: API Keys (First few chars or None) ---")
#     print(f"OpenAI Key loaded: {str(OPENAI_API_KEY)[:5] if OPENAI_API_KEY else None}")
#     print(f"Anthropic Key loaded: {str(ANTHROPIC_API_KEY)[:5] if ANTHROPIC_API_KEY else None}")
#     print(f"Google Key loaded: {str(GOOGLE_API_KEY)[:5] if GOOGLE_API_KEY else None}")
#     print(f"OpenRouter Key loaded: {str(OPENROUTER_API_KEY)[:5] if OPENROUTER_API_KEY else None}")
#     print("----------------------------------------------------")

#     # Test individual fetch functions if needed
#     # print("--- Testing Prism individually ---")
#     # test_prompt_prism = "What are the latest advancements in AI-driven drug discovery?"
#     # prism_response = await fetch_prism(test_prompt_prism)
#     # print(f"Prism Response: {prism_response}\n")

#     print("--- Testing Orchestration ---")
#     # orchestration_prompt = "Write a short story about a robot who discovers it can dream."
#     orchestration_prompt = "why does my wife hate me" # The prompt from your log
    
#     all_results = await run_orchestration(orchestration_prompt)
    
#     print("\n--- Orchestration Results ---")
#     if all_results and "responses" in all_results:
#         for agent, response_text in all_results["responses"].items():
#             print(f"Agent: {agent}\nResponse: {response_text}\n--------------------")
#         print(f"Quorum: {all_results.get('quorum')}")
#     else:
#         print("Orchestration did not return expected results.")

# if __name__ == "__main__":
#     # Ensure your .env file is correctly set up with all API keys. For example:
#     # OPENAI_API_KEY="sk-..."
#     # ANTHROPIC_API_KEY="sk-ant-..."
#     # GOOGLE_API_KEY="AIza..."
#     # OPENROUTER_API_KEY="sk-or-..."
#     # 
#     # To run the example: python your_script_name.py
#     asyncio.run(main())