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

def aggregate_responses(responses):
    """
    Aggregate the list of responses into a unified output with meta-structure.
    """
    confidence, majority, dissenting = analyze_agreement(responses)
    merged_answer = ensemble_merge(responses)

    return {
        "consensus": merged_answer,
        "majority_view": majority,
        "minority_view": dissenting if dissenting else None,
        "confidence": confidence,
        "note": "Maestro strives for synthesis, but preserves dissent when perfection cannot be reached."
    }
