import os
from dotenv import load_dotenv

# Load API keys from .env file
load_dotenv()

OPENAI_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
GOOGLE_KEY = os.getenv("GOOGLE_API_KEY")

USE_REAL_MODELS = True

def query_openai(prompt: str) -> str:
    if not USE_REAL_MODELS:
        return "[MOCK OPENAI RESPONSE]"

    import openai
    openai.api_key = OPENAI_KEY

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=800
        )
        return response['choices'][0]['message']['content']
    except Exception as e:
        return f"[ERROR: OpenAI API failed: {e}]"

def query_anthropic(prompt: str) -> str:
    if not USE_REAL_MODELS:
        return "[MOCK CLAUDE/ANTHROPIC RESPONSE]"

    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    try:
        response = client.messages.create(
            model="claude-3-opus-20240229",
            max_tokens=800,
            temperature=0.7,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        return response.content[0].text
    except Exception as e:
        return f"[ERROR: Anthropic API failed: {e}]"

def query_gemini(prompt: str) -> str:
    if not USE_REAL_MODELS:
        return "[MOCK GOOGLE GEMINI RESPONSE]"

    import google.generativeai as genai
    genai.configure(api_key=GOOGLE_KEY)

    try:
        model = genai.GenerativeModel("gemini-pro")
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        return f"[ERROR: Google Gemini API failed: {e}]"

# Optionally add future placeholders for Axiom (Copilot/Azure) and Axion (Grok)

def query_axiom(prompt: str) -> str:
    return "[MOCK MICROSOFT COPILOT RESPONSE]"

def query_axion(prompt: str) -> str:
    return "[MOCK GROK/XAI RESPONSE - No Public API Yet]"
