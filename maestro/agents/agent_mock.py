# Placeholder for mock agent personalities
class MockAgent2:
    def respond(self, prompt: str) -> str:
        return f"[MockAgent2] In my view, the key to '{prompt}' is empathy and systems thinking."

class MockAgent3:
    def respond(self, prompt: str) -> str:
        return f"[MockAgent3] Historically, questions like '{prompt}' have driven scientific revolution."

from .agent_openai import OpenAIAgent
