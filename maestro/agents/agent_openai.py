# Placeholder for OpenAI agent wrapper
import os


class OpenAIAgent:
    def __init__(self, model="gpt-3.5-turbo"):
        self.model = model

    def respond(self, prompt: str) -> str:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return f"[OpenAI Agent Placeholder] Response to: '{prompt}' — (API key not set)"

        try:
            import openai
            client = openai.OpenAI(api_key=api_key)
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
