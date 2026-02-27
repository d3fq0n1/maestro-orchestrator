import os
import sys
import asyncio
from dotenv import load_dotenv

# Load .env from the same directory as this script
dotenv_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=dotenv_path)

# Allow imports from the project root so the maestro package is visible
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from maestro.agents.sol import Sol
from maestro.agents.aria import Aria
from maestro.agents.prism import Prism
from maestro.agents.tempagent import TempAgent

# === Council ===
# Each agent is a self-contained module. Swap models, timeouts, or
# entire providers by changing the instance here.
COUNCIL = [
    Sol(),
    Aria(),
    Prism(),
    TempAgent(),
]


# === Orchestration Runner ===
async def run_orchestration(prompt: str) -> dict:
    try:
        print(f"[Orchestrator] Prompt received: {prompt}")
        results = await asyncio.gather(
            *(agent.fetch(prompt) for agent in COUNCIL)
        )
        print("[Orchestrator] All results received.")

        responses = {agent.name: result for agent, result in zip(COUNCIL, results)}

        successful = {k: v for k, v in responses.items() if not v.startswith("[")}
        quorum = {
            "consensus": "Consensus logic pending...",
            "successful_votes": len(successful),
            "total_agents": len(COUNCIL),
        }

        return {
            "responses": responses,
            "quorum": quorum,
        }

    except Exception as e:
        print(f"[ERROR] Orchestration Exception: {type(e).__name__} - {e}")
        error_responses = {agent.name: "Orchestration Error" for agent in COUNCIL}
        return {
            "responses": error_responses,
            "quorum": {
                "consensus": "Orchestration Failed",
                "successful_votes": 0,
                "total_agents": len(COUNCIL),
            },
        }


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
    for agent_name, response in result["responses"].items():
        print(f"Agent: {agent_name}\nResponse: {response}\n{'-' * 20}")
    print(f"Quorum: {result['quorum']}")


if __name__ == "__main__":
    if validate_keys():
        asyncio.run(main())
    else:
        print("One or more API keys missing. Check your .env file.")
