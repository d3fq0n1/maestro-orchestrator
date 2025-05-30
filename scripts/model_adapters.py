# model_adapters.py

import asyncio
import random
from typing import Optional

# Simulated delay and mock responses for fallback
MOCK_RESPONSES = {
    "Sol": "The meaning of life is to create meaning.",
    "Axion": "There is no inherent meaning, only what we make of it.",
    "Aria": "Life is a narrative shaped by connection and purpose.",
    "Prism": "Meaning emerges from complexity and reflection.",
    "Axiom": "Meaning is a logical structure derived from experience."
}

# Simulated real API call (to be replaced with actual API integration)
async def query_model(model_name: str, question: str) -> str:
    try:
        # TODO: Replace with real API logic per model
        await asyncio.sleep(random.uniform(0.2, 1.2))
        if random.random() < 0.15:
            raise TimeoutError("Simulated API timeout")
        return f"{model_name} says: '{MOCK_RESPONSES.get(model_name, 'Unknown response')}'"
    except Exception as e:
        print(f"[WARN] {model_name} failed, using fallback: {e}")
        return f"{model_name} fallback: '{MOCK_RESPONSES.get(model_name, 'No response available')}'"

# Dispatcher to handle parallel model execution
def get_council_adapter():
    async def ask_council(question: str) -> dict:
        tasks = []
        council_names = ["Sol", "Axion", "Aria", "Prism", "Axiom"]
        for name in council_names:
            tasks.append(query_model(name, question))

        responses = await asyncio.gather(*tasks)
        return {name: response for name, response in zip(council_names, responses)}

    return ask_council

# Test runner
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python model_adapters.py \"Your question here\"")
    else:
        question = sys.argv[1]
        adapter = get_council_adapter()
        results = asyncio.run(adapter(question))
        for model, reply in results.items():
            print(f"[{model}] {reply}")
