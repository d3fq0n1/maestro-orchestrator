# Placeholder foimport openai
from config import OPENAI_API_KEY

# Create a client object (OpenAI SDK v1.x+)
client = openai.OpenAI(api_key=OPENAI_API_KEY)

class OpenAIAgent:
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = model

    def respond(self, prompt: str) -> str:
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a wise AI agent participating in a multi-agent reasoning system."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            return f"[OpenAI Agent Error] {str(e)}"
r OpenAI agent wrapper
