
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
import os
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(dotenv_path=env_path)

print("ENV loaded:", os.getenv("OPENAI_API_KEY"))

print("ENV loaded:", os.getenv("OPENAI_API_KEY"))


import os
from agents.sol import get_response as sol_response
from agents.aria import get_response as aria_response
#from agents.prism import get_response as prism_response commented out until google stops being an asshole
from agents.openrouter_temporaryagent import get_response as openrouter_response


agents = {
    "Sol": sol_response,
    "Aria": aria_response,
    "openrouter_temporaryagent": openrouter_response
}


question = "How should synthetic intelligence handle conflicting moral frameworks between cultures?"

print("\n=== Livefire Orchestration Test ===")
for name, agent_fn in agents.items():
    try:
        print(f"\n{name} responds:")
        response = agent_fn(question)
        print(response)
    except Exception as e:
        print(f"[{name} ERROR] {e}")
