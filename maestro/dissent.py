"""
Dissent Analysis — Measures how agents disagree with each other.

NCG catches when all agents drift together from the headless baseline
(silent collapse). Dissent analysis catches the other signal: when agents
genuinely disagree with each other within a session.

This module produces two things R2 needs:
  1. An internal_agreement score (0.0-1.0) that feeds into NCG's silent
     collapse detector — closing the loop between "agents agree" and
     "but their agreement might be conformity."
  2. Per-pair and per-agent dissent breakdowns so R2 can identify which
     agents are outliers and whether disagreement is healthy (diverse
     reasoning) or pathological (one agent is broken).

It also provides cross-session analysis by reading from the session
history data layer, tracking which agents dissent most often and whether
dissent patterns are changing over time.
"""

from dataclasses import dataclass, field
from itertools import combinations


@dataclass
class PairwiseDissent:
    """Semantic distance between two specific agents."""
    agent_a: str
    agent_b: str
    distance: float  # 0.0 = identical, 1.0 = maximally different


@dataclass
class AgentDissentProfile:
    """How much a single agent diverges from the rest of the council."""
    agent_name: str
    mean_distance_to_others: float  # average distance to all other agents
    is_outlier: bool                # True if this agent is significantly further than the rest


@dataclass
class DissentReport:
    """Complete dissent analysis for a single orchestration session."""
    prompt: str
    internal_agreement: float       # 0.0 = total disagreement, 1.0 = perfect agreement
    pairwise: list                  # list of PairwiseDissent
    agent_profiles: list            # list of AgentDissentProfile
    outlier_agents: list            # names of agents flagged as outliers
    dissent_level: str              # "none", "low", "moderate", "high"
    agent_count: int


class DissentAnalyzer:
    """
    Measures internal disagreement across agent responses.

    Uses the same semantic distance approach as the NCG DriftDetector
    (Jaccard fallback when sentence-transformers is unavailable), but
    applies it pairwise across agents rather than against a headless
    baseline.
    """

    def __init__(self, similarity_model=None):
        self._model = similarity_model
        self._model_loaded = False

    def _load_model(self):
        if self._model_loaded:
            return
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            self._model_loaded = True
        except ImportError:
            self._model = None
            self._model_loaded = True

    def _semantic_distance(self, text_a: str, text_b: str) -> float:
        """0.0 = identical, 1.0 = maximally different."""
        self._load_model()

        if self._model is not None:
            from sentence_transformers import util
            embeddings = self._model.encode([text_a, text_b], convert_to_tensor=True)
            similarity = util.pytorch_cos_sim(embeddings[0], embeddings[1]).item()
            return round(1.0 - max(0.0, min(1.0, similarity)), 4)

        # Fallback: Jaccard distance
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a and not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return round(1.0 - (len(intersection) / len(union)), 4)

    def analyze(self, prompt: str, agent_responses: dict) -> DissentReport:
        """
        Analyze internal dissent across all agent responses.

        Args:
            prompt: The original prompt
            agent_responses: dict of {agent_name: response_text}

        Returns:
            DissentReport with pairwise distances, per-agent profiles,
            outlier detection, and the internal_agreement score that
            NCG's silent collapse detector consumes.
        """
        agents = list(agent_responses.keys())
        agent_count = len(agents)

        # --- Pairwise distances ---
        pairwise = []
        for a, b in combinations(agents, 2):
            dist = self._semantic_distance(agent_responses[a], agent_responses[b])
            pairwise.append(PairwiseDissent(agent_a=a, agent_b=b, distance=dist))

        # --- Per-agent profiles ---
        # For each agent, compute mean distance to all others
        agent_distances = {name: [] for name in agents}
        for pair in pairwise:
            agent_distances[pair.agent_a].append(pair.distance)
            agent_distances[pair.agent_b].append(pair.distance)

        profiles = []
        mean_distances = {}
        for name in agents:
            dists = agent_distances[name]
            mean_dist = sum(dists) / len(dists) if dists else 0.0
            mean_distances[name] = mean_dist
            profiles.append(AgentDissentProfile(
                agent_name=name,
                mean_distance_to_others=round(mean_dist, 4),
                is_outlier=False,  # set below
            ))

        # --- Outlier detection ---
        # An agent is an outlier if its mean distance to others exceeds
        # the group mean by more than 1.5x. Needs at least 3 agents to
        # be meaningful.
        outlier_agents = []
        if agent_count >= 3 and mean_distances:
            group_mean = sum(mean_distances.values()) / len(mean_distances)
            threshold = group_mean * 1.5 if group_mean > 0 else 0.5
            for profile in profiles:
                if profile.mean_distance_to_others > threshold:
                    profile.is_outlier = True
                    outlier_agents.append(profile.agent_name)

        # --- Internal agreement score ---
        # Inverse of mean pairwise distance. 1.0 = all agents identical,
        # 0.0 = all agents maximally different.
        all_distances = [p.distance for p in pairwise]
        mean_pairwise = sum(all_distances) / len(all_distances) if all_distances else 0.0
        internal_agreement = round(1.0 - mean_pairwise, 4)

        # --- Dissent level classification ---
        if mean_pairwise < 0.1:
            dissent_level = "none"
        elif mean_pairwise < 0.3:
            dissent_level = "low"
        elif mean_pairwise < 0.6:
            dissent_level = "moderate"
        else:
            dissent_level = "high"

        return DissentReport(
            prompt=prompt,
            internal_agreement=internal_agreement,
            pairwise=pairwise,
            agent_profiles=profiles,
            outlier_agents=outlier_agents,
            dissent_level=dissent_level,
            agent_count=agent_count,
        )

    def analyze_across_sessions(self, session_records: list) -> dict:
        """
        Analyze dissent patterns across multiple sessions from the
        session history data layer.

        Args:
            session_records: list of SessionRecord objects (or dicts
                with agent_responses and prompt keys)

        Returns:
            dict with cross-session dissent metrics:
              - per_agent: each agent's average dissent across sessions
              - trend: whether overall dissent is rising, falling, or stable
              - sessions_analyzed: count
        """
        agent_dissents = {}  # {agent_name: [mean_distance, ...]}
        session_agreements = []

        for record in session_records:
            responses = record.agent_responses if hasattr(record, "agent_responses") else record.get("agent_responses", {})
            prompt = record.prompt if hasattr(record, "prompt") else record.get("prompt", "")

            if len(responses) < 2:
                continue

            report = self.analyze(prompt, responses)
            session_agreements.append(report.internal_agreement)

            for profile in report.agent_profiles:
                if profile.agent_name not in agent_dissents:
                    agent_dissents[profile.agent_name] = []
                agent_dissents[profile.agent_name].append(profile.mean_distance_to_others)

        per_agent = {}
        for name, dists in agent_dissents.items():
            per_agent[name] = {
                "mean_dissent": round(sum(dists) / len(dists), 4) if dists else 0.0,
                "sessions": len(dists),
            }

        # Trend: compare first half vs second half of sessions
        trend = "stable"
        if len(session_agreements) >= 4:
            mid = len(session_agreements) // 2
            first_half = sum(session_agreements[:mid]) / mid
            second_half = sum(session_agreements[mid:]) / (len(session_agreements) - mid)
            diff = second_half - first_half
            if diff > 0.1:
                trend = "converging"   # agreement increasing
            elif diff < -0.1:
                trend = "diverging"    # agreement decreasing

        return {
            "sessions_analyzed": len(session_agreements),
            "mean_agreement": round(sum(session_agreements) / len(session_agreements), 4) if session_agreements else 0.0,
            "trend": trend,
            "per_agent": per_agent,
        }
