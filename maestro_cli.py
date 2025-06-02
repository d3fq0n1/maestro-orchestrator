
import argparse
import json
import os
from collections import Counter
from datetime import datetime
import random
# import openai  # Uncomment when ready to use real LLMs

DEFAULT_AGENTS = ["Sol", "Axion", "Aria", "Prism", "Axiom"]
DEFAULT_ROLES = ["scribe", "dissenter", "strategist", "analyst", "arbiter"]

def rotate_roles(agents, roles):
    return {agent: roles[i % len(roles)] for i, agent in enumerate(agents)}

def simulate_vote(agent, role):
    # Placeholder for actual logic per role
    # Could replace with real LLM call here
    # response = openai.ChatCompletion.create(...)
    if role == "dissenter":
        return random.choices(["yes", "no"], weights=[0.3, 0.7])[0]
    elif role == "arbiter":
        return "yes"
    else:
        return random.choice(["yes", "no"])

def run_round(agents, roles, quorum, round_num):
    role_map = rotate_roles(agents, roles)
    votes = {agent: simulate_vote(agent, role_map[agent]) for agent in agents}
    yes_count = sum(1 for v in votes.values() if v == "yes")
    quorum_required = (quorum / 100) * len(agents)
    met = yes_count >= quorum_required

    return {
        "round": round_num,
        "agents": agents,
        "roles": role_map,
        "votes": votes,
        "yes_votes": yes_count,
        "quorum_percent": quorum,
        "quorum_met": met,
        "timestamp": datetime.now().isoformat()
    }

def print_round_summary(summary, verbose):
    print(f"\nRound {summary['round']} Summary:")
    if verbose:
        for agent in summary["agents"]:
            print(f"  {agent} ({summary['roles'][agent]}): {summary['votes'][agent]}")
    print(f"  {'✔' if summary['quorum_met'] else '✘'} Quorum {'met' if summary['quorum_met'] else 'not met'} ({summary['yes_votes']} / {len(summary['agents'])})")

def save_log(all_rounds, log_dir="scripts/council_session/logs"):
    os.makedirs(log_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(log_dir, f"multi_session_{ts}.json")
    with open(path, "w") as f:
        json.dump(all_rounds, f, indent=2)
    print(f"Session log saved to {path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Maestro CLI (multi-round)")
    parser.add_argument("--agents", nargs="+", default=DEFAULT_AGENTS, help="List of agent names.")
    parser.add_argument("--quorum", type=int, default=66, help="Quorum percentage required.")
    parser.add_argument("--rounds", type=int, default=3, help="Number of rounds to simulate.")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--save-log", action="store_true", help="Save session results to file.")

    args = parser.parse_args()
    rounds_data = []

    for i in range(1, args.rounds + 1):
        summary = run_round(args.agents, DEFAULT_ROLES, args.quorum, i)
        print_round_summary(summary, args.verbose)
        rounds_data.append(summary)

    if args.save_log:
        save_log(rounds_data)


def append_history(entries, history_file="history/session_log.jsonl"):
    os.makedirs(os.path.dirname(history_file), exist_ok=True)
    with open(history_file, "a") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

# Add persistent history tracking
append_history(rounds_data)
