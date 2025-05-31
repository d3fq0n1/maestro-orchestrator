import os
from dotenv import load_dotenv

env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

print("OPENAI_API_KEY:", os.getenv("OPENAI_API_KEY"))
print("GEMINI_API_KEY:", os.getenv("GEMINI_API_KEY"))
print("ANTHROPIC_API_KEY:", os.getenv("ANTHROPIC_API_KEY"))
