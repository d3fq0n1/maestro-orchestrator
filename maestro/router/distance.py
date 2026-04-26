"""
Context Router — composite distance metric, admission function,
bundle composition, and trust-annotated preamble rendering.

See docs/architecture/router-distance.md for the specification and
docs/architecture/distance-dissent.md for the forced-rotation
extension.

Conflicts-resolution defaults flagged in router-distance.md:
  - Q11 (a): only d_embed is live day 1; d_graph, d_causal,
             d_counter return configurable constants.
  - Q12 (c): global per-tier tau defaults with per-agent overrides.
  - Q13 (a): XML-style <context-bundle>...</context-bundle> preamble
             with inner JSON; <user-prompt>...</user-prompt> wraps
             the sanitized user input.

This module has no business logic yet. Every method is a stub
documenting the spec it will implement.
"""

from dataclasses import dataclass, field
from enum import Enum
import math
from typing import Optional

from maestro.router.graph import GraphView, NullGraphView


class Tier(str, Enum):
    CARTRIDGE = "cartridge"
    WHIRLPOOL = "whirlpool"
    WEIGHT_PRIOR = "weight_prior"


# --- Distance metric ---


@dataclass
class DistanceWeights:
    """Composite distance weights. Must sum to 1.0 (enforced at load).

    Day 1 defaults biased toward d_embed (the only live component).
    """

    w_embed: float = 0.7
    w_graph: float = 0.15
    w_causal: float = 0.1
    w_counter: float = 0.05


@dataclass
class DistanceComponents:
    """Per-component distance scores for one (Q, C) pair.

    All values in [0, 1]. Useful for pre-admit ledger logging.
    """

    d_embed: float
    d_graph: float
    d_causal: float
    d_counter: float

    def composite(self, weights: DistanceWeights) -> float:
        """Linear combination of components, clamped to ``[0, 1]``.

        Weights are expected to sum to 1.0 per
        ``router-distance.md`` §Composite distance metric; the
        clamp is defensive against weight configurations that
        drift from that invariant or against component values that
        themselves stray slightly out of range.
        """
        total = (
            weights.w_embed * self.d_embed
            + weights.w_graph * self.d_graph
            + weights.w_causal * self.d_causal
            + weights.w_counter * self.d_counter
        )
        return max(0.0, min(1.0, total))


class DistanceMetric:
    """Composite distance function used by the admission criterion.

    Live components:
      - d_embed: cosine distance via the embedder already in use by
        maestro/dissent.py and maestro/ncg/drift.py. No new embedding
        client is introduced.

    Stubbed components (return configurable constants):
      - d_graph: 0.5 default. Future: walk the Librarian supersedes/
        revokes graph + shared-tag edges.
      - d_causal: 0.5 default. Future: co-occurrence-with-flip over
        the R2 ledger.
      - d_counter: 0.5 default. Future: perturbed-query counterfactual.
    """

    def __init__(
        self,
        weights: Optional[DistanceWeights] = None,
        graph_view: Optional[GraphView] = None,
        graph_stub_value: float = 0.5,
        causal_stub_value: float = 0.5,
        counter_stub_value: float = 0.5,
        max_hops: int = 6,
        normalization_k: float = 3.0,
    ):
        """
        Parameters
        ----------
        weights:
            Composite distance weights. Defaults to ``DistanceWeights()``.
        graph_view:
            The graph the BFS in :meth:`d_graph` walks. When ``None``
            (default), a :class:`NullGraphView` is bound so callers
            constructed without a graph still work. Under
            ``NullGraphView`` the ``d_graph`` method returns
            ``graph_stub_value`` directly without invoking the BFS —
            today's behavior is preserved (option R from the step 3
            design discussion). When a real ``GraphView`` is wired
            (e.g. ``CompositeGraphView``), the BFS runs and the
            constant is ignored.
        graph_stub_value, causal_stub_value, counter_stub_value:
            Configurable constants returned by the corresponding
            stub components. ``graph_stub_value`` is also the
            fallback when ``graph_view`` is ``NullGraphView``.
        max_hops:
            BFS depth cap. Beyond ``max_hops`` the walk gives up and
            ``d_graph`` returns 1.0 (max distance). Default 6, which
            saturates the normalization at ``1 - exp(-2) ≈ 0.865``.
        normalization_k:
            Curve constant for ``1 - exp(-hops/k)``. Default 3.0:
            hops 0/1/2/3/4/5/6 → 0.00 / 0.28 / 0.49 / 0.63 / 0.74 /
            0.81 / 0.86. Lower k makes nearby hops more distant
            faster; higher k flattens.
        """
        self._weights = weights or DistanceWeights()
        self._graph: GraphView = graph_view if graph_view is not None else NullGraphView()
        self._graph_stub = graph_stub_value
        self._causal_stub = causal_stub_value
        self._counter_stub = counter_stub_value
        self._max_hops = max_hops
        self._k = normalization_k

    # ---- live component ----

    def d_embed(self, query_embedding: list, claim_embedding: list) -> float:
        """Cosine distance ``1 - cos(θ)`` between the two vectors,
        clamped to ``[0, 1]``.

        The method takes pre-computed embedding vectors. Producing
        the embeddings is the caller's responsibility; the embedder
        used by ``maestro/dissent.py`` and ``maestro/ncg/drift.py``
        is the natural source. No new embedding client is introduced
        here.

        Edge cases:

        * Empty vector on either side → 1.0 (max distance).
        * Zero-norm vector on either side → 1.0 (undefined cosine,
          treated as max distance).
        * Dimension mismatch → ``ValueError``.
        * Cosine is clamped to ``[-1, 1]`` before forming
          ``1 - cos``; the result is then clamped to ``[0, 1]`` to
          honor the spec's "all values in [0, 1]" requirement.
          Anti-correlated vectors (cos < 0) therefore saturate at
          1.0 rather than producing the raw value of 2.
        """
        if not query_embedding or not claim_embedding:
            return 1.0
        if len(query_embedding) != len(claim_embedding):
            raise ValueError(
                f"embedding dimension mismatch: "
                f"query={len(query_embedding)} claim={len(claim_embedding)}"
            )
        dot = 0.0
        qsq = 0.0
        csq = 0.0
        for q, c in zip(query_embedding, claim_embedding):
            dot += q * c
            qsq += q * q
            csq += c * c
        if qsq == 0.0 or csq == 0.0:
            return 1.0
        cosine = dot / math.sqrt(qsq * csq)
        cosine = max(-1.0, min(1.0, cosine))
        return max(0.0, min(1.0, 1.0 - cosine))

    # ---- stubbed components (configurable constants) ----

    def d_graph(self, query_tags: list, claim_node_id: str) -> float:
        """Graph distance from the query tag-set to a claim node.

        Multi-source BFS over ``self._graph``: seeded simultaneously
        from every anchor returned by
        ``self._graph.anchors_for_tags(query_tags)``, expanded
        breadth-first up to ``self._max_hops``, normalized via
        ``1 - exp(-hops/k)``.

        Returns
        -------
        float in [0.0, 1.0]
            * 0.0 when ``claim_node_id`` is itself one of the
              query's anchors (zero hops).
            * ``1 - exp(-hops/k)`` when reached at ``hops``
              (1 ≤ hops ≤ max_hops).
            * 1.0 when no anchors resolve, when the BFS exhausts
              reachable nodes without finding the claim, or when
              the claim is past ``max_hops``.

        Behavior under ``NullGraphView`` is unchanged from step 3:
        the stub constant is returned without invoking the BFS. This
        preserves today's behavior for callers that haven't been
        updated to inject a real graph view (option R from the step
        3 design).
        """
        if isinstance(self._graph, NullGraphView):
            return self._graph_stub

        anchors = list(self._graph.anchors_for_tags(query_tags))
        if not anchors:
            return 1.0

        anchor_set = set(anchors)
        if claim_node_id in anchor_set:
            return 0.0  # 1 - exp(0) = 0

        visited: set = set(anchor_set)
        frontier: set = set(anchor_set)

        for hops in range(1, self._max_hops + 1):
            next_frontier: set = set()
            for node in frontier:
                for edge in self._graph.neighbors(node):
                    # Undirected traversal: advance to whichever
                    # endpoint isn't the node we arrived from.
                    other = edge.dst if edge.src == node else edge.src
                    if other in visited:
                        continue
                    next_frontier.add(other)
            if not next_frontier:
                return 1.0
            if claim_node_id in next_frontier:
                return 1.0 - math.exp(-hops / self._k)
            visited.update(next_frontier)
            frontier = next_frontier

        return 1.0  # claim not reached within max_hops

    def d_causal(self, query_text: str, claim_text: str) -> float:
        """STUB: returns configurable constant."""
        # TODO: once R2 pre-admit + post-hoc history is large enough,
        # score co-occurrence-with-flip over historical sessions.
        return self._causal_stub

    def d_counter(self, query_text: str, claim_text: str) -> float:
        """STUB: returns configurable constant."""
        # TODO: perturb the query, recompute relevance, return the
        # magnitude of relevance shift.
        return self._counter_stub

    # ---- composite ----

    def components(
        self,
        query_embedding: list,
        claim_embedding: list,
        query_tags: list,
        query_text: str,
        claim_text: str,
        claim_node_id: str,
    ) -> DistanceComponents:
        """Compute all four components for one (Q, C) pair.

        The placeholder ``claim_tags`` / ``claim_manifest_hash``
        parameters from step 4's pre-BFS shape are dropped: the
        graph encodes claim→tag edges already, and the caller has
        the candidate object in hand to produce ``claim_node_id``.

        ``query_text`` and ``claim_text`` are kept even though the
        d_causal and d_counter implementations are configurable-
        constant stubs day 1. Their eventual live implementations
        will read text, so the input shape is fixed now to avoid a
        future signature churn.
        """
        return DistanceComponents(
            d_embed=self.d_embed(query_embedding, claim_embedding),
            d_graph=self.d_graph(query_tags, claim_node_id),
            d_causal=self.d_causal(query_text, claim_text),
            d_counter=self.d_counter(query_text, claim_text),
        )


# --- Admission function ---


@dataclass
class TauPolicy:
    """Per-tier admission thresholds.

    Resolution (Q12 = c):
      1. Per-agent override via WeightHost.admission_policy.tau
      2. Global default below.

    Defaults per router-distance.md §Admission Function.
    """

    cartridge: float = 0.8
    whirlpool: float = 0.4
    weight_prior: float = 0.3


@dataclass
class AdmissionCriterion:
    """One evaluation of admit(C, agent).

    product = trust * relevance
    score   = product / (distance + epsilon)
    admit   = score >= tau(agent, tier)
    """

    tier: Tier
    trust: float
    relevance: float
    distance: float
    score: float
    tau: float
    admit: bool


# --- Admitted claim + bundle ---


@dataclass
class AdmittedClaim:
    """A single claim included in a per-agent bundle.

    Rendered into the <claims> array of the preamble. Fields match
    router-distance.md §Block shape. Exact serialization is handled
    by ``render_preamble``.
    """

    tier: Tier
    id: str                              # manifest_hash | item_id | "tag:..."
    trust: float
    relevance: float
    distance: float
    body_excerpt: str = ""
    claim_summary: str = ""
    domain_tags: list = field(default_factory=list)
    provenance: list = field(default_factory=list)
    long_shot: bool = False
    # tier-specific metadata
    kind: Optional[str] = None            # Cartridge only
    ring: Optional[int] = None            # Whirlpool only
    corroborators: Optional[int] = None   # Whirlpool only
    whirlpool_id: Optional[str] = None    # Whirlpool only


@dataclass
class BundleRequest:
    """Inputs needed to assemble one agent's bundle."""

    session_id: str
    agent_name: str
    user_prompt: str
    query_embedding: list
    query_tags: list
    is_dissenter: bool = False
    forced_rotation_session_index: int = 0


@dataclass
class ContextBundle:
    """A completed bundle ready to render.

    Outputs:
      - admitted: claims the Weight is authoritatively given
      - tail: long-shot claims (subset with long_shot=True)
      - rejected_summary: per-tier summary of rejected candidates
      - threat_flags: any flags detected during assembly
      - rendered_preamble: the XML-wrapped preamble string
    """

    session_id: str
    agent_name: str
    admitted: list                   # list[AdmittedClaim]
    tail: list                       # subset of admitted with long_shot=True
    rejected_summary: dict
    tau_in_force: TauPolicy
    distance_weights_in_force: DistanceWeights
    threat_flags: list = field(default_factory=list)
    rendered_preamble: str = ""


# --- Router ---


class ContextRouter:
    """Per-session, per-agent bundle assembler.

    Runs inside the ``pre_orchestration`` hook. The orchestrator
    consumes the rendered preamble from each ContextBundle and
    prepends it to the prompt before ``agent.fetch()``.

    Dependencies (injected, not imported at module scope):
      - a Librarian (for Cartridge candidates)
      - zero or more Whirlpools (for vortex candidates)
      - an embedder (shared with dissent / ncg.drift)
      - an R2Engine with a ``pre_admit`` method (new interface)
      - an AdmissionGuard (new module, not yet scaffolded)
    """

    DEFAULT_K_MAX_WHIRLPOOL = 8
    DEFAULT_K_MAX_WEIGHT_PRIOR = 3
    DEFAULT_K_TAIL = 2
    DEFAULT_K_TAIL_DISSENTER = 4
    EPSILON = 0.01
    DEFAULT_PREAMBLE_BYTE_CAP = 32 * 1024   # 32 KiB

    def __init__(
        self,
        librarian,
        whirlpools: list,
        embedder,
        r2_engine,
        admission_guard,
        distance_metric: Optional[DistanceMetric] = None,
        default_tau: Optional[TauPolicy] = None,
    ):
        self._librarian = librarian
        self._whirlpools = whirlpools
        self._embedder = embedder
        self._r2 = r2_engine
        self._guard = admission_guard
        self._distance = distance_metric or DistanceMetric()
        self._default_tau = default_tau or TauPolicy()

    # ---- top-level assembly ----

    async def assemble(self, request: BundleRequest) -> ContextBundle:
        """Build a per-agent bundle.

        Algorithm (router-distance.md §Bundle-Composition Algorithm):
          1. infer_query_tags (cheap classifier + hook-provided tags)
          2. collect_candidates (Librarian, Whirlpools, Weight priors)
          3. score each candidate (distance + trust + relevance)
          4. admit under tau, capped by per-tier k_max
          5. draw long-shot tail (k_tail, per-agent)
          6. render_preamble
          7. R2Engine.pre_admit(...)
          8. AdmissionGuard.gate(bundle)
          9. return the bundle (orchestrator prepends preamble)
        """
        # TODO
        raise NotImplementedError

    # ---- step helpers (listed for traceability with spec) ----

    def infer_query_tags(self, prompt: str) -> list:
        """Cheap bag-of-tags classifier. Placeholder — spec defers to
        embedding-based k-NN once pre-admit data exists."""
        # TODO
        raise NotImplementedError

    async def collect_candidates(self, request: BundleRequest) -> list:
        """Collect candidate claims from all three tiers.

        Calls:
          - Librarian.candidates(query_tags, kind_filter=None)
          - Whirlpool.query(emb(Q), query_tags, k=50) for matching Whirlpools
          - synth_weight_prior_candidates(query_tags)
        """
        # TODO
        raise NotImplementedError

    def synth_weight_prior_candidates(self, query_tags: list) -> list:
        """One synthetic candidate per query tag, trust=0.5 baseline."""
        # TODO
        raise NotImplementedError

    def score_candidate(self, request: BundleRequest, candidate) -> AdmissionCriterion:
        """Compute trust, relevance, distance, score, and admit."""
        # TODO
        raise NotImplementedError

    def resolve_tau(self, agent_name: str, is_dissenter: bool) -> TauPolicy:
        """Resolve per-agent tau with cascade.

        Dissenter path (distance-dissent.md §Moderate-distance bundle):
          - tau[cartridge]   = 0.5
          - tau[whirlpool]   = 0.2
          - tau[weight_prior] = 0.2
        """
        # TODO
        raise NotImplementedError

    def apply_admission(
        self,
        criteria: list,
        k_max_whirlpool: int,
        k_max_weight_prior: int,
        dissenter_moderate_boost: bool,
    ) -> list:
        """Admit per criterion, apply per-tier k_max, return list[AdmittedClaim]."""
        # TODO: moderate-distance +0.1 boost for dissenter in 50-80th percentile
        raise NotImplementedError

    def draw_long_shot_tail(
        self,
        rejected: list,
        k_tail: int,
    ) -> list:
        """Sample from rejected candidates, prob ∝ trust * relevance.

        Partition: rejected candidates with trust*relevance >= 0.3 and
        distance > median(admitted distance). Without replacement.
        """
        # TODO
        raise NotImplementedError

    # ---- preamble ----

    def sanitize_user_prompt(self, prompt: str) -> str:
        """Entity-escape bundle markers inside the user prompt.

        See vortex-threat-model.md §T-1. The NCG headless baseline
        receives the ORIGINAL prompt, not the sanitized one — this
        method is only for the agents' transport.
        """
        # TODO: replace <context-bundle, </context-bundle>, <claims>,
        # </claims>, <user-prompt, </user-prompt> with entity escapes
        raise NotImplementedError

    def render_preamble(
        self,
        bundle: ContextBundle,
        sanitized_user_prompt: str,
        forced_rotation: Optional[dict] = None,
    ) -> str:
        """Render the XML-style preamble + <user-prompt> block.

        Format per router-distance.md §Block shape:

            <context-bundle version="1">
              <admission>{...}</admission>
              <claims>[{...}, ...]</claims>
            </context-bundle>
            <user-prompt>...</user-prompt>

        When ``forced_rotation`` is provided, the admission JSON
        includes a ``forced_rotation`` sub-object.

        Enforces the preamble byte cap and drops admitted claims in
        increasing-distance order until the cap is met, recording
        the drop in the admission summary.
        """
        # TODO
        raise NotImplementedError
