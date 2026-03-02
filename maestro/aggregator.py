from collections import Counter


def analyze_agreement(responses):
    """
    Determines level of agreement among agents.
    Returns (confidence, majority_response, dissenting_responses)
    """
    counts = Counter(responses)
    most_common = counts.most_common(1)[0]
    majority = most_common[0]
    count = most_common[1]

    confidence = "High" if count == 3 else "Medium" if count == 2 else "Low"
    dissenting = [resp for resp in responses if resp != majority]

    return confidence, majority, dissenting


def ensemble_merge(responses):
    """
    Synthesize all responses into a unified answer.
    """
    merged = " | ".join(responses)
    return f"Synthesized Answer: {merged}"


def aggregate_responses(responses, ncg_drift_report=None, dissent_report=None):
    """
    Aggregate the list of responses into a unified output with meta-structure.

    When an NCG drift report is provided, the output includes diversity
    benchmark data — measuring how far the conversational agents have
    drifted from the headless baseline. This is the silent collapse signal.

    When a dissent report is provided, the output includes internal
    agreement metrics — how much agents disagreed with each other,
    which agents are outliers, and the overall dissent level.
    """
    confidence, majority, dissenting = analyze_agreement(responses)
    merged_answer = ensemble_merge(responses)

    result = {
        "consensus": merged_answer,
        "majority_view": majority,
        "minority_view": dissenting if dissenting else None,
        "confidence": confidence,
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
