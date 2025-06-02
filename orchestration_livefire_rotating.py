
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import argparse
import random
import time
from dotenv import load_dotenv
load_dotenv()

from agents.sol import get_response as sol_response
from agents.aria import get_response as aria_response
from agents.prism import get_response as prism_response

agent_pool = {
    "Sol": sol_response,
    "Aria": aria_response,
    "Prism": prism_response
}

def main(rounds, prompt):
    agents = list(agent_pool.keys())

    print(f"\n=== Maestro Livefire Rotating Council Test ({rounds} rounds) ===")
    print(f"\nPrompt: {prompt}")

    for round_num in range(1, rounds + 1):
        print(f"\n--- Round {round_num} ---")
        random.shuffle(agents)
        for name in agents:
            print(f"\n{name} responds:")
            try:
                response = agent_pool[name](prompt)
                print(response)
            except Exception as e:
                print(f"[{name} ERROR] {e}")
            time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run rotating livefire agent rounds.")
    parser.add_argument("--rounds", type=int, default=5, help="Number of council rounds to simulate")
    parser.add_argument("--prompt", type=str, help="The question or prompt to ask the agents")
    args = parser.parse_args()

    if not args.prompt:
        args.prompt = input("Enter your council prompt: ")

    main(args.rounds, args.prompt)
