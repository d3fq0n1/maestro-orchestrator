from itertools import combinations

QUORUM_THRESHOLD = 0.66
SIMILARITY_THRESHOLD = 0.5  # pairwise distance below this = "in agreement"


def _cluster_by_similarity(agent_names, pairwise_distances):
    """
    Group agents into clusters where all members are within
    SIMILARITY_THRESHOLD of each other. Returns the largest cluster
    (list of agent names) and remaining agents.

    Uses greedy single-linkage: start with the first agent, add any agent
    whose mean distance to current cluster members is below the threshold.
    Repeat for remaining agents to find all clusters, then return the largest.
    """
    if not agent_names:
        return [], []

    # Build a distance lookup: (agent_a, agent_b) -> distance
    dist_map = {}
    for pair in pairwise_distances:
        dist_map[(pair.agent_a, pair.agent_b)] = pair.distance
        dist_map[(pair.agent_b, pair.agent_a)] = pair.distance

    remaining = list(agent_names)
    clusters = []

    while remaining:
        cluster = [remaining.pop(0)]
        changed = True
        while changed:
            changed = False
            for agent in remaining[:]:
                # Mean distance from this agent to all current cluster members
                dists = [dist_map.get((agent, m), 1.0) for m in cluster]
                mean_dist = sum(dists) / len(dists)
                if mean_dist < SIMILARITY_THRESHOLD:
                    cluster.append(agent)
                    remaining.remove(agent)
                    changed = True
        clusters.append(cluster)

    clusters.sort(key=len, reverse=True)
    largest = clusters[0]
    minority = [a for c in clusters[1:] for a in c]
    return largest, minority


def analyze_agreement(responses, dissent_report=None):
    """
    Determines level of agreement among agents.

    When a dissent_report is available, uses semantic similarity clustering
    to determine which agents agree (pairwise distance below threshold).
    Falls back to exact string matching when no dissent data is available.

    Returns (confidence, agreement_ratio, majority_response, dissenting_responses)
    where agreement_ratio is a float 0.0-1.0 representing the fraction of
    agents in the largest agreeing cluster.
    """
    if dissent_report is not None and dissent_report.pairwise:
        agent_names = [p.agent_name for p in dissent_report.agent_profiles]
        majority_cluster, minority_agents = _cluster_by_similarity(
            agent_names, dissent_report.pairwise,
        )
        total = len(agent_names)
        agreement_ratio = len(majority_cluster) / total if total > 0 else 0.0

        # Pick the first agent's response from the majority cluster as the
        # representative majority view. The full synthesis comes from
        # ensemble_merge anyway.
        majority_view = None
        minority_views = []
        if isinstance(responses, dict):
            resp_dict = responses
        else:
            # responses is a list — map by position to agent names
            resp_dict = dict(zip(agent_names, responses))

        if majority_cluster:
            majority_view = resp_dict.get(majority_cluster[0], "")
        minority_views = [resp_dict.get(a, "") for a in minority_agents]

        if agreement_ratio >= QUORUM_THRESHOLD:
            confidence = "High"
        elif agreement_ratio >= 0.5:
            confidence = "Medium"
        else:
            confidence = "Low"

        return confidence, agreement_ratio, majority_view, minority_views

    # Fallback: exact string matching (no dissent data available)
    if isinstance(responses, dict):
        resp_list = list(responses.values())
    else:
        resp_list = list(responses)

    from collections import Counter
    counts = Counter(resp_list)
    most_common = counts.most_common(1)[0]
    majority = most_common[0]
    count = most_common[1]
    total = len(resp_list)

    agreement_ratio = count / total if total > 0 else 0.0
    if agreement_ratio >= QUORUM_THRESHOLD:
        confidence = "High"
    elif agreement_ratio >= 0.5:
        confidence = "Medium"
    else:
        confidence = "Low"

    dissenting = [resp for resp in resp_list if resp != majority]
    return confidence, agreement_ratio, majority, dissenting


def ensemble_merge(responses):
    """
    Synthesize all responses into a unified answer.
    """
    if isinstance(responses, dict):
        items = list(responses.values())
    else:
        items = list(responses)
    merged = " | ".join(items)
    return f"Synthesized Answer: {merged}"


def aggregate_responses(responses, ncg_drift_report=None, dissent_report=None):
    """
    Aggregate the list of responses into a unified output with meta-structure.

    When an NCG drift report is provided, the output includes diversity
    benchmark data — measuring how far the conversational agents have
    drifted from the headless baseline. This is the silent collapse signal.

    When a dissent report is provided, the output includes internal
    agreement metrics — how much agents disagreed with each other,
    which agents are outliers, and the overall dissent level. The dissent
    data also drives semantic quorum logic.
    """
    confidence, agreement_ratio, majority, dissenting = analyze_agreement(
        responses, dissent_report,
    )
    merged_answer = ensemble_merge(responses)

    quorum_met = agreement_ratio >= QUORUM_THRESHOLD

    result = {
        "consensus": merged_answer,
        "majority_view": majority,
        "minority_view": dissenting if dissenting else None,
        "confidence": confidence,
        "agreement_ratio": round(agreement_ratio, 4),
        "quorum_met": quorum_met,
        "quorum_threshold": QUORUM_THRESHOLD,
        "note": "Maestro strives for synthesis, but preserves dissent when perfection cannot be reached.",
    }

    if dissent_report is not None:
        result["dissent"] = {
            "internal_agreement": dissent_report.internal_agreement,
            "dissent_level": dissent_report.dissent_level,
            "outlier_agents": dissent_report.outlier_agents,
            "pairwise": [
                {
                    "agents": [p.agent_a, p.agent_b],
                    "distance": p.distance,
                }
                for p in dissent_report.pairwise
            ],
            "agent_profiles": [
                {
                    "agent": p.agent_name,
                    "mean_distance": p.mean_distance_to_others,
                    "is_outlier": p.is_outlier,
                }
                for p in dissent_report.agent_profiles
            ],
        }

    if ncg_drift_report is not None:
        result["ncg_benchmark"] = {
            "ncg_model": ncg_drift_report.ncg_model,
            "mean_drift": ncg_drift_report.mean_semantic_distance,
            "max_drift": ncg_drift_report.max_semantic_distance,
            "silent_collapse": ncg_drift_report.silent_collapse_detected,
            "compression_alert": ncg_drift_report.compression_alert,
            "per_agent": [
                {
                    "agent": sig.agent_name,
                    "drift": sig.semantic_distance,
                    "compression": sig.compression_ratio,
                    "tier": sig.analysis_tier,
                }
                for sig in ncg_drift_report.agent_signals
            ],
        }

        if ncg_drift_report.silent_collapse_detected:
            result["note"] = (
                "WARNING: Silent collapse detected. All agents agree, but their "
                "outputs have drifted significantly from the headless baseline. "
                "Consensus may reflect RLHF conformity rather than genuine reasoning."
            )

    return result
