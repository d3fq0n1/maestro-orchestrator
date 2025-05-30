
import argparse
import random

def simulate_agents(num_agents, quorum_percent, verbose):
    responses = []
    for i in range(num_agents):
        response = random.choice(['yes', 'no'])
        responses.append(response)
        if verbose:
            print(f"Agent {i+1}: {response}")

    yes_votes = responses.count('yes')
    required = (quorum_percent / 100) * num_agents

    print(f"\nTotal 'yes' votes: {yes_votes} / {num_agents}")
    if yes_votes >= required:
        print(f"✔ Quorum met (≥ {quorum_percent}%)")
    else:
        print(f"✘ Quorum not met (requires {quorum_percent}% agreement)")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Maestro Orchestrator Mock CLI")
    parser.add_argument('--agents', type=int, default=3, help="Number of mock agents")
    parser.add_argument('--quorum', type=int, default=66, help="Quorum percentage required")
    parser.add_argument('--verbose', action='store_true', help="Print individual agent responses")

    args = parser.parse_args()
    simulate_agents(args.agents, args.quorum, args.verbose)
