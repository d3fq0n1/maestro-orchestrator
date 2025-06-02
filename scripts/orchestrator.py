
import argparse
from collections import Counter
import random
import json

def simulate_agent_vote(agent_name):
    """Simulate an agent decision."""
    return random.choice(["yes", "no"])

def calculate_consensus(votes, quorum_percent):
    """Determine if quorum is met."""
    vote_counts = Counter(votes.values())
    yes_votes = vote_counts["yes"]
    quorum_required = (quorum_percent / 100) * len(votes)
    return yes_votes >= quorum_required, yes_votes, vote_counts

def run_orchestration(agents, quorum_percent, verbose=False):
    """Run the quorum decision process."""
    votes = {agent: simulate_agent_vote(agent) for agent in agents}

    if verbose:
        for agent, vote in votes.items():
            print(f"Agent {agent}: {vote}")

    consensus_met, yes_votes, vote_counts = calculate_consensus(votes, quorum_percent)
    result = {
        "votes": votes,
        "yes_votes": yes_votes,
        "quorum_percent": quorum_percent,
        "quorum_met": consensus_met,
        "summary": "✔ Quorum met" if consensus_met else "✘ Quorum not met",
    }
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run a Maestro-Orchestrator session.")
    parser.add_argument("--agents", nargs="+", default=["Sol", "Axion", "Aria", "Prism", "Axiom"], help="List of agent names.")
    parser.add_argument("--quorum", type=int, default=66, help="Quorum percentage required.")
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")
    parser.add_argument("--json-out", type=str, help="Optional JSON output file.")

    args = parser.parse_args()
    result = run_orchestration(args.agents, args.quorum, verbose=args.verbose)

    print(f"\n{result['summary']}: {result['yes_votes']} / {len(result['votes'])} voted YES.")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Saved results to: {args.json_out}")
