
import os
import requests

def get_response(prompt, model="mistralai/mistral-7b-instruct", temperature=0.7):
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        return "[MOCK-OPENROUTER] I am a temporary logic-focused agent. This is a simulated reply."

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": "https://openrouter.ai",
        "X-Title": "Maestro-Orchestrator",
        "Content-Type": "application/json"
    }
    url = "https://openrouter.ai/api/v1/chat/completions"

    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a temporary OpenRouter agent tasked with providing logical, concise, and structured replies. You are focused, reserved, and grounded in deductive reasoning."},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature
    }

    try:
        response = requests.post(url, headers=headers, json=data)
        result = response.json()
        print("[openrouter_temporaryagent DEBUG] Full response:", result)

        if "choices" not in result:
            return "[openrouter_temporaryagent ERROR] 'choices' key not found in response."

        return result["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[openrouter_temporaryagent ERROR] {e}"
