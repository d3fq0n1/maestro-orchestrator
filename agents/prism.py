import os
import requests

def get_response(prompt, model="gemini-pro", temperature=0.7):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return "[MOCK-PRISM] I am Prism. This is a simulated analysis."

    url = "https://generativelanguage.googleapis.com/v1beta/gemini-pro:generateContent"
    headers = {"Content-Type": "application/json"}
    params = {"key": api_key}
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature}
    }

    try:
        response = requests.post(url, headers=headers, params=params, json=data)
        json_data = response.json()
        print("[PRISM DEBUG] Full JSON Response:", json_data)

        candidates = json_data.get("candidates", [])
        if not candidates:
            return "[Prism WARNING] No content returned."
        return candidates[0]["content"]["parts"][0]["text"]
    except Exception as e:
        return f"[Prism ERROR] {e}"
