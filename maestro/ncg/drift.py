"""
NCG Drift Detector — Measures distance between headless and conversational outputs.

This is the signal nobody else is building. Internal dissent (R2) catches
when agents disagree with each other. Drift detection catches when ALL
conversational agents silently agree on something shaped more by RLHF
conformity than by actual reasoning.

The headless output is the ground truth baseline — not because it's "more
correct," but because the DISTANCE between headless output and conversational
output tells you how much the conversational layer is compressing the
answer space. When that distance grows, something is being lost.

Two tiers of analysis:
  1. Semantic drift  — embedding distance (available now, all models)
  2. Token-level drift — logprob divergence (available for models that
     expose logprobs, e.g. OpenAI)
"""

from dataclasses import dataclass, field


@dataclass
class DriftSignal:
    """Result of comparing a single conversational output against NCG baseline."""
    agent_name: str
    semantic_distance: float  # 0.0 = identical, 1.0 = maximally different
    compression_ratio: float  # conversational length / headless length
    ncg_model: str
    analysis_tier: str  # "semantic" or "token_level"
    token_drift: dict = field(default_factory=dict)  # populated when logprobs available


@dataclass
class DriftReport:
    """Aggregate drift analysis across all conversational agents."""
    prompt: str
    ncg_content: str
    ncg_model: str
    agent_signals: list  # list of DriftSignal
    mean_semantic_distance: float
    max_semantic_distance: float
    silent_collapse_detected: bool  # True when agents agree but all drift from NCG
    compression_alert: bool  # True when conversational outputs significantly shorter


class DriftDetector:
    """
    Compares conversational agent outputs against NCG headless baseline.

    Operates at two tiers:
      - Semantic: Uses sentence embeddings to measure distance. Works for
        all models. This is your primary signal at the conversational
        metadata level.
      - Token-level: When logprobs are available (e.g. OpenAI), compares
        probability distributions to detect where the conversational
        model's certainty diverges from the headless model's uncertainty.
        This is the bridge to full token-level analysis.
    """

    def __init__(self, similarity_model=None):
        self._model = similarity_model
        self._model_loaded = False

    def _load_model(self):
        """Lazy-load the embedding model to avoid import cost at startup."""
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
        """
        Compute semantic distance between two texts.
        Returns 0.0 (identical) to 1.0 (maximally different).
        Falls back to naive word overlap when sentence-transformers unavailable.
        """
        self._load_model()

        if self._model is not None:
            from sentence_transformers import util
            embeddings = self._model.encode([text_a, text_b], convert_to_tensor=True)
            similarity = util.pytorch_cos_sim(embeddings[0], embeddings[1]).item()
            return round(1.0 - max(0.0, min(1.0, similarity)), 4)

        # Fallback: Jaccard distance on word sets
        words_a = set(text_a.lower().split())
        words_b = set(text_b.lower().split())
        if not words_a and not words_b:
            return 0.0
        intersection = words_a & words_b
        union = words_a | words_b
        return round(1.0 - (len(intersection) / len(union)), 4)

    def _compression_ratio(self, conversational: str, headless: str) -> float:
        """
        Ratio of conversational output length to headless output length.
        Values < 1.0 mean the conversational output is shorter (compressed).
        """
        headless_len = len(headless.split())
        if headless_len == 0:
            return 1.0
        return round(len(conversational.split()) / headless_len, 4)

    def _analyze_token_drift(self, ncg_metadata: dict) -> dict:
        """
        Extract token-level drift signal when logprobs are available.
        This is where conversational-level analysis bridges to token-level.
        """
        if not ncg_metadata.get("logprobs_available"):
            return {}

        logprobs = ncg_metadata.get("logprobs", [])
        if not logprobs:
            return {}

        # Compute uncertainty metrics from headless generation
        probs = [entry["logprob"] for entry in logprobs]
        mean_logprob = sum(probs) / len(probs) if probs else 0.0

        # Find high-uncertainty tokens (where the model was least certain)
        uncertain_tokens = [
            entry for entry in logprobs
            if entry["logprob"] < -2.0  # arbitrary threshold: < ~13% confidence
        ]

        # Find tokens with strong alternative candidates
        contested_tokens = []
        for entry in logprobs:
            alts = entry.get("top_alternatives", [])
            if alts and len(alts) > 0:
                top_alt_prob = alts[0]["logprob"]
                gap = entry["logprob"] - top_alt_prob
                if gap < 0.5:  # chosen token barely beat the alternative
                    contested_tokens.append({
                        "chosen": entry["token"],
                        "alternative": alts[0]["token"],
                        "gap": round(gap, 4),
                    })

        return {
            "mean_logprob": round(mean_logprob, 4),
            "total_tokens": len(probs),
            "uncertain_token_count": len(uncertain_tokens),
            "contested_token_count": len(contested_tokens),
            "contested_tokens": contested_tokens[:10],  # cap for readability
        }

    def analyze(
        self,
        prompt: str,
        ncg_output: dict,
        conversational_outputs: dict,
        internal_agreement: float = None,
    ) -> DriftReport:
        """
        Compare conversational agent outputs against NCG headless baseline.

        Args:
            prompt: The original prompt
            ncg_output: dict from HeadlessGenerator.generate()
            conversational_outputs: dict of {agent_name: response_text}
            internal_agreement: optional float (0-1) from R2 showing how
                much the conversational agents agreed with each other

        Returns:
            DriftReport with per-agent signals and aggregate metrics
        """
        ncg_content = ncg_output["content"]
        ncg_model = ncg_output["model"]
        ncg_metadata = ncg_output.get("metadata", {})

        has_logprobs = ncg_metadata.get("logprobs_available", False)
        token_drift = self._analyze_token_drift(ncg_metadata)

        signals = []
        for agent_name, response_text in conversational_outputs.items():
            distance = self._semantic_distance(ncg_content, response_text)
            compression = self._compression_ratio(response_text, ncg_content)
            tier = "token_level" if has_logprobs else "semantic"

            signals.append(DriftSignal(
                agent_name=agent_name,
                semantic_distance=distance,
                compression_ratio=compression,
                ncg_model=ncg_model,
                analysis_tier=tier,
                token_drift=token_drift if has_logprobs else {},
            ))

        distances = [s.semantic_distance for s in signals]
        mean_dist = round(sum(distances) / len(distances), 4) if distances else 0.0
        max_dist = max(distances) if distances else 0.0

        compressions = [s.compression_ratio for s in signals]
        mean_compression = sum(compressions) / len(compressions) if compressions else 1.0

        # Silent collapse: agents agree with each other (low internal dissent)
        # but all drift significantly from the headless baseline.
        # This is the signal that RLHF conformity is compressing the answer space.
        high_agreement = internal_agreement is not None and internal_agreement > 0.8
        high_drift = mean_dist > 0.3
        silent_collapse = high_agreement and high_drift

        # Compression alert: conversational outputs are significantly shorter,
        # meaning the models are compressing away nuance.
        compression_alert = mean_compression < 0.5

        return DriftReport(
            prompt=prompt,
            ncg_content=ncg_content,
            ncg_model=ncg_model,
            agent_signals=signals,
            mean_semantic_distance=mean_dist,
            max_semantic_distance=max_dist,
            silent_collapse_detected=silent_collapse,
            compression_alert=compression_alert,
        )
