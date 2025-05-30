# run_council_session.py

import json
import datetime
from council_config import COUNCIL_MEMBERS

def get_mock_response(model_name, question):
    return {
        "model": model_name,
        "claim": f"{model_name}'s synthesized claim for: {question}",
        "evidence": f"Supporting reasoning from {model_name} on: {question}",
        "confidence": 0.8 + 0.05 * (hash(model_name) % 4)
    }

def run_council_session(question):
    timestamp = datetime.datetime.now().isoformat()
    responses = [get_mock_response(member["name"], question) for member in COUNCIL_MEMBERS]

    claims = [resp["claim"] for resp in responses]
    majority_claim = max(set(claims), key=claims.count)
    consensus_count = claims.count(majority_claim)
    consensus_ratio = consensus_count / len(claims)
    consensus_reached = consensus_ratio >= 0.66

    for resp in responses:
        resp.update({
            "timestamp": timestamp,
            "question": question,
            "consensus": resp["claim"] == majority_claim
        })

    session_log_path = "logs/session_log.json"
    with open(session_log_path, "w") as f:
        json.dump(responses, f, indent=2)

    print(f"Council session complete. Consensus reached: {consensus_reached} ({consensus_count}/{len(claims)}).\nLog saved to {session_log_path}.")
    return responses, majority_claim if consensus_reached else None

def generate_markdown_summary(responses, majority_claim, output_file="docs/session_summary.md"):
    timestamp = responses[0]["timestamp"] if responses else ""
    question = responses[0]["question"] if responses else ""

    lines = [
        f"# Maestro Council Session — {timestamp}\n",
        f"**Question:** {question}\n",
        f"**Consensus Reached:** {'Yes' if majority_claim else 'No'}\n",
        f"**Majority Claim:** {majority_claim if majority_claim else 'N/A'}\n",
        "\n## Council Responses\n"
    ]

    for resp in responses:
        lines.extend([
            f"### {resp['model']}\n",
            f"- **Claim:** {resp['claim']}\n",
            f"- **Evidence:** {resp['evidence']}\n",
            f"- **Confidence:** {resp['confidence']}\n",
            f"- **Consensus:** {'Yes' if resp['consensus'] else 'No'}\n",
            "\n"
        ])

    with open(output_file, "w") as f:
        f.writelines(lines)
    print(f"Markdown summary saved to {output_file}.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python run_council_session.py \"Your question here\"")
    else:
        question = sys.argv[1]
        responses, majority_claim = run_council_session(question)
        generate_markdown_summary(responses, majority_claim)