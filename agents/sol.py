
import os
from openai import OpenAI

def get_response(prompt, model="gpt-3.5-turbo", temperature=0.7):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "[MOCK-SOL] I am Sol. This is a simulated response."

    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are Sol, the orchestrator's voice and language engine, tasked with clear synthesis of ideas."},
            {"role": "user", "content": prompt}
        ],
        temperature=temperature
    )
    return response.choices[0].message.content.strip()
