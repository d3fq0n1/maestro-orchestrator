from collections import Counter
from sentence_transformers import SentenceTransformer, util

# Lightweight model - fast and accurate for similarity
model = SentenceTransformer('all-MiniLM-L6-v2')

def determine_quorum_hybrid(agent_outputs):
    """
    Determine if a quorum is reached based on either:
    1. Explicit vote agreement (e.g. 'support:Sol')
    2. Semantic similarity in summaries
    """
    votes = [entry["vote"] for entry in agent_outputs]
    vote_counter = Counter(votes)

    # Rule 1: Explicit support
    for vote_token, count in vote_counter.items():
        if "support:" in vote_token and count >= 3:
            target_agent = vote_token.split(":")[1]
            target_summary = next((o["summary"] for o in agent_outputs if o["agent"] == target_agent), None)
            return True, target_summary, votes

    # Rule 2: Semantic similarity quorum
    summaries = [entry["summary"] for entry in agent_outputs]
    embeddings = model.encode(summaries, convert_to_tensor=True)
    sim_matrix = util.pytorch_cos_sim(embeddings, embeddings)

    # Count how many summaries have ≥ 0.85 similarity with at least 2 others
    similar_counts = (sim_matrix >= 0.85).sum(dim=1) - 1
    if (similar_counts >= 2).sum().item() >= 3:
        most_agreed_idx = similar_counts.argmax().item()
        return True, summaries[most_agreed_idx], votes

    return False, None, votes


def extract_dissent(agent_outputs, quorum_summary):
    """
    Returns dict of dissenting agent names and their responses.
    Includes both explicit dissent and semantic mismatch.
    """
    dissenters = {}
    for output in agent_outputs:
        if output["vote"].startswith("dissent"):
            dissenters[output["agent"]] = output["response"]
        elif quorum_summary and output["summary"] != quorum_summary:
            dissenters[output["agent"]] = output["response"]
    return dissenters
