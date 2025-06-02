
import os
import requests

def get_response(prompt, model="claude-sonnet-4-0", temperature=0.7):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return "[MOCK-ARIA] I am Aria. This is a simulated nuance reply."

    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }
    data = {
        "model": model,
        "max_tokens": 500,
        "temperature": temperature,
        "messages": [
            {"role": "user", "content": prompt}
        ]
    }

    try:
        response = requests.post("https://api.anthropic.com/v1/messages", headers=headers, json=data)
        json_data = response.json()
        print("[ARIA DEBUG] Full JSON Response:", json_data)

        content = json_data.get("content", [])
        if not content:
            return "[Aria WARNING] No content returned."
        return "".join(part.get("text", "") for part in content)
    except Exception as e:
        return f"[Aria ERROR] {e}"
