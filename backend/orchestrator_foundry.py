import os
import sys
import asyncio
from dotenv import load_dotenv

# Load .env — prefer MAESTRO_ENV_FILE (set in Docker for volume-backed persistence),
# then fall back to the same directory as this script.
dotenv_path = os.environ.get("MAESTRO_ENV_FILE") or os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path)

# Allow imports from the project root so the maestro package is visible
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from maestro.agents.sol import Sol
from maestro.agents.aria import Aria
from maestro.agents.prism import Prism
from maestro.agents.tempagent import TempAgent
from maestro.orchestrator import run_orchestration_async
from maestro.ncg.generator import (
    OpenAIHeadlessGenerator,
    AnthropicHeadlessGenerator,
    MockHeadlessGenerator,
)

# === Council ===
# Each agent is a self-contained module. Swap models, timeouts, or
# entire providers by changing the instance here.
COUNCIL = [
    Sol(),
    Aria(),
    Prism(),
    TempAgent(),
]


def _select_headless_generator():
    """Pick the best available headless generator based on API keys."""
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIHeadlessGenerator()
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicHeadlessGenerator()
    return MockHeadlessGenerator()


# === Orchestration Runner ===
async def run_orchestration(prompt: str) -> dict:
    """
    Thin wrapper that passes the live council and best available headless
    generator into the core orchestration pipeline. All analysis (dissent,
    NCG, R2, session logging) runs on every request.
    """
    return await run_orchestration_async(
        prompt=prompt,
        agents=COUNCIL,
        ncg_enabled=True,
        session_logging=True,
        headless_generator=_select_headless_generator(),
    )


# === API Key Validation ===
def validate_keys() -> bool:
    required = {
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "ANTHROPIC_API_KEY": os.getenv("ANTHROPIC_API_KEY"),
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY"),
        "OPENROUTER_API_KEY": os.getenv("OPENROUTER_API_KEY"),
    }
    missing = [name for name, val in required.items() if not val]
    if missing:
        print(f"[Startup Error] Missing API keys: {', '.join(missing)}")
        return False
    return True


# === Main Execution ===
async def main():
    prompt = "explain why taco bell rightly became the only restaurant in demolition man"
    result = await run_orchestration(prompt)

    print("\n--- Orchestration Results ---")
    for name, response in result.get("named_responses", {}).items():
        print(f"Agent: {name}\nResponse: {response}\n{'-' * 20}")

    final = result.get("final_output", {})
    print(f"Consensus: {final.get('consensus', 'N/A')}")
    print(f"Confidence: {final.get('confidence', 'N/A')}")
    if "r2" in final:
        print(f"R2 Grade: {final['r2']['grade']} "
              f"(confidence: {final['r2']['confidence_score']})")


if __name__ == "__main__":
    if validate_keys():
        asyncio.run(main())
    else:
        print("One or more API keys missing. Check your .env file.")
