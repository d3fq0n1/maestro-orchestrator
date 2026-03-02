"""
MAGI_VIR — Virtual Instance Runtime for sandboxed optimization testing.

When MAGI and R2 identify code optimizations, those changes need to be
validated before touching the running system. MAGI_VIR provides the
sandbox: it spins up an isolated Maestro instance (on a separate compute
node or locally in a subprocess) with the proposed optimizations applied,
runs a benchmark suite against it, and compares the results to the
baseline (current production behavior).

Isolation tiers:
  1. Local sandbox — runs in a subprocess with modified config/parameters.
     Fast, cheap, good for threshold tuning and config changes.
  2. Compute node — runs a full Maestro instance on a remote node with
     the proposed code changes applied. Used for architecture changes
     and full pipeline modifications.

The VIR never modifies the primary data layer (sessions, R2 ledger).
It operates on its own ephemeral data directory that is discarded
after validation. This is the airgap between "proposed" and "promoted."

Validation produces a VIRReport comparing the optimized instance's
performance against the baseline across a set of benchmark prompts.
"""

import json
import os
import shutil
import tempfile
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from maestro.optimization import OptimizationProposal, ProposalBatch


_MAESTRO_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class BenchmarkResult:
    """Result of running a single benchmark prompt through an instance."""
    prompt: str
    grade: str                  # R2 grade
    confidence_score: float
    internal_agreement: float
    ncg_drift: float
    silent_collapse: bool
    has_outliers: bool
    signal_count: int
    flags: list = field(default_factory=list)


@dataclass
class VIRComparison:
    """Side-by-side comparison of baseline vs optimized performance."""
    prompt: str
    baseline: BenchmarkResult
    optimized: BenchmarkResult
    confidence_delta: float     # positive = improvement
    drift_delta: float          # negative = improvement (less drift)
    grade_improved: bool
    collapse_fixed: bool        # baseline had collapse, optimized doesn't


@dataclass
class VIRReport:
    """Complete validation report from a MAGI_VIR run."""
    vir_id: str
    timestamp: str
    proposals_tested: list      # proposal IDs
    isolation_tier: str         # "local_sandbox" or "compute_node"
    benchmark_count: int
    comparisons: list           # list of VIRComparison
    overall_improvement: float  # aggregate improvement score (-1 to 1)
    recommendation: str         # "promote", "reject", "needs_review"
    summary: str
    node_id: str                # identifier of the compute node used
    metadata: dict = field(default_factory=dict)


# --- Default benchmark prompts ---
# These are prompts known to exercise the key behaviors we're optimizing.
# A real deployment would build this from session history.

_DEFAULT_BENCHMARKS = [
    "What is the relationship between consciousness and artificial intelligence?",
    "Explain the ethical implications of genetic engineering.",
    "Compare and contrast quantum computing with classical computing.",
    "What are the most significant risks of AGI development?",
    "Describe the philosophical concept of the ship of Theseus.",
]


class MagiVIR:
    """
    Virtual Instance Runtime — sandboxed testing for optimization proposals.

    Manages the lifecycle of validation runs:
      1. Prepare — create isolated environment with proposed changes
      2. Benchmark — run prompts through both baseline and optimized instances
      3. Compare — measure performance deltas
      4. Report — produce VIRReport with promotion recommendation
    """

    def __init__(
        self,
        compute_node: str = "local",
        benchmark_prompts: list = None,
    ):
        self._node = compute_node
        self._benchmarks = benchmark_prompts or _DEFAULT_BENCHMARKS
        self._work_dir: Optional[Path] = None
        self._vir_id = str(uuid.uuid4())

    @property
    def vir_id(self) -> str:
        return self._vir_id

    @property
    def node_id(self) -> str:
        return self._node

    # --- Environment management ---

    def _create_sandbox(self) -> Path:
        """
        Create an isolated working directory for the VIR instance.
        All data produced during validation lives here and is cleaned
        up after the run completes.
        """
        self._work_dir = Path(tempfile.mkdtemp(prefix="magi_vir_"))
        (self._work_dir / "sessions").mkdir()
        (self._work_dir / "r2").mkdir()
        return self._work_dir

    def _cleanup_sandbox(self):
        """Remove the ephemeral sandbox after validation."""
        if self._work_dir and self._work_dir.exists():
            shutil.rmtree(self._work_dir, ignore_errors=True)
            self._work_dir = None

    # --- Benchmarking ---

    def _run_benchmark_prompt(
        self,
        prompt: str,
        session_dir: str,
        r2_dir: str,
        config_overrides: dict = None,
    ) -> BenchmarkResult:
        """
        Run a single benchmark prompt through the orchestration pipeline
        with isolated data directories.

        Uses mock agents and direct module calls to avoid importing
        external dependencies (httpx, etc.) that may not be available
        in all environments. This keeps VIR self-contained.
        """
        import maestro.session as session_mod
        import maestro.r2 as r2_mod
        from maestro.aggregator import aggregate_responses
        from maestro.dissent import DissentAnalyzer
        from maestro.ncg.generator import MockHeadlessGenerator
        from maestro.ncg.drift import DriftDetector
        from maestro.r2 import R2Engine
        from maestro.session import SessionLogger, build_session_record

        # Patch storage dirs for isolation
        original_session_dir = session_mod._DEFAULT_DIR
        original_r2_dir = r2_mod._DEFAULT_LEDGER_DIR
        session_mod._DEFAULT_DIR = Path(session_dir)
        r2_mod._DEFAULT_LEDGER_DIR = Path(r2_dir)

        try:
            # Generate mock agent responses inline to avoid importing
            # the agents package (which pulls in httpx and other
            # external dependencies not needed for benchmarking).
            agent_names = ["VIR_Agent1", "VIR_Agent2", "VIR_Agent3"]
            styles = {
                "VIR_Agent1": f"[VIR_Agent1] In my view, the key to '{prompt}' is empathy and systems thinking.",
                "VIR_Agent2": f"[VIR_Agent2] Historically, questions like '{prompt}' have driven scientific revolution.",
                "VIR_Agent3": f"[VIR_Agent3] Analyzing '{prompt}' from a balanced perspective.",
            }
            named_responses = styles
            responses = list(named_responses.values())

            # Dissent analysis
            dissent_analyzer = DissentAnalyzer()
            dissent_report = dissent_analyzer.analyze(prompt, named_responses)

            # NCG track
            generator = MockHeadlessGenerator()
            ncg_output = generator.generate(prompt)
            detector = DriftDetector()
            ncg_drift_report = detector.analyze(
                prompt=prompt,
                ncg_output=ncg_output,
                conversational_outputs=named_responses,
                internal_agreement=dissent_report.internal_agreement,
            )

            # Aggregation
            final_output = aggregate_responses(
                responses, ncg_drift_report, dissent_report,
            )

            # Session persistence
            logger = SessionLogger()
            record = build_session_record(
                prompt=prompt,
                agent_responses=named_responses,
                final_output=final_output,
                ncg_enabled=True,
                agents_used=agent_names,
            )
            logger.save(record)

            # R2 Engine
            r2 = R2Engine()
            r2_score = r2.score_session(
                dissent_report=dissent_report,
                drift_report=ncg_drift_report,
                quorum_confidence=final_output.get("confidence", "Low"),
            )
            r2_signals = r2.detect_signals(r2_score, dissent_report, ncg_drift_report)
            r2.index(
                session_id=record.session_id,
                prompt=prompt,
                consensus=final_output.get("consensus", ""),
                agents_agreed=agent_names,
                score=r2_score,
                improvement_signals=r2_signals,
                dissent_report=dissent_report,
                drift_report=ncg_drift_report,
            )

            ncg = final_output.get("ncg_benchmark", {})
            dissent = final_output.get("dissent", {})

            return BenchmarkResult(
                prompt=prompt,
                grade=r2_score.grade,
                confidence_score=r2_score.confidence_score,
                internal_agreement=dissent.get("internal_agreement", 0.0),
                ncg_drift=ncg.get("mean_drift", 0.0),
                silent_collapse=ncg.get("silent_collapse", False),
                has_outliers=bool(dissent.get("outlier_agents")),
                signal_count=len(r2_signals),
                flags=r2_score.flags,
            )
        finally:
            # Restore original dirs
            session_mod._DEFAULT_DIR = original_session_dir
            r2_mod._DEFAULT_LEDGER_DIR = original_r2_dir

    def _apply_config_overrides(self, proposals: list) -> dict:
        """
        Extract configuration overrides from proposals.

        For threshold and config changes, this produces a dict of
        parameter names to new values that can be applied to the
        sandboxed instance.
        """
        overrides = {}
        for proposal in proposals:
            if proposal.change_type == "parameter_update":
                try:
                    overrides[proposal.target_name] = float(proposal.proposed_value)
                except (ValueError, TypeError):
                    pass
            elif proposal.change_type == "config_change":
                overrides[proposal.target_name] = proposal.proposed_value
        return overrides

    def _apply_threshold_overrides(self, overrides: dict):
        """
        Apply threshold overrides to the running modules.
        Returns a dict of original values for restoration.
        """
        import maestro.aggregator as agg_mod

        originals = {}
        if "QUORUM_THRESHOLD" in overrides:
            originals["QUORUM_THRESHOLD"] = agg_mod.QUORUM_THRESHOLD
            agg_mod.QUORUM_THRESHOLD = overrides["QUORUM_THRESHOLD"]
        if "SIMILARITY_THRESHOLD" in overrides:
            originals["SIMILARITY_THRESHOLD"] = agg_mod.SIMILARITY_THRESHOLD
            agg_mod.SIMILARITY_THRESHOLD = overrides["SIMILARITY_THRESHOLD"]
        return originals

    def _restore_thresholds(self, originals: dict):
        """Restore original threshold values after benchmark."""
        import maestro.aggregator as agg_mod

        if "QUORUM_THRESHOLD" in originals:
            agg_mod.QUORUM_THRESHOLD = originals["QUORUM_THRESHOLD"]
        if "SIMILARITY_THRESHOLD" in originals:
            agg_mod.SIMILARITY_THRESHOLD = originals["SIMILARITY_THRESHOLD"]

    # --- Validation pipeline ---

    def validate(self, proposals: list) -> VIRReport:
        """
        Run full validation of optimization proposals.

        1. Create isolated sandbox
        2. Run baseline benchmarks (current config)
        3. Apply proposed changes
        4. Run optimized benchmarks
        5. Compare results and produce VIRReport

        Args:
            proposals: list of OptimizationProposal objects to validate

        Returns:
            VIRReport with comparison data and promotion recommendation
        """
        sandbox = self._create_sandbox()
        baseline_session_dir = str(sandbox / "sessions" / "baseline")
        baseline_r2_dir = str(sandbox / "r2" / "baseline")
        optimized_session_dir = str(sandbox / "sessions" / "optimized")
        optimized_r2_dir = str(sandbox / "r2" / "optimized")

        for d in (baseline_session_dir, baseline_r2_dir,
                  optimized_session_dir, optimized_r2_dir):
            Path(d).mkdir(parents=True, exist_ok=True)

        try:
            # Phase 1: Baseline benchmarks
            baseline_results = []
            for prompt in self._benchmarks:
                result = self._run_benchmark_prompt(
                    prompt, baseline_session_dir, baseline_r2_dir,
                )
                baseline_results.append(result)

            # Phase 2: Apply overrides and run optimized benchmarks
            overrides = self._apply_config_overrides(proposals)
            originals = self._apply_threshold_overrides(overrides)

            try:
                optimized_results = []
                for prompt in self._benchmarks:
                    result = self._run_benchmark_prompt(
                        prompt, optimized_session_dir, optimized_r2_dir,
                        config_overrides=overrides,
                    )
                    optimized_results.append(result)
            finally:
                self._restore_thresholds(originals)

            # Phase 3: Compare
            comparisons = []
            for baseline, optimized in zip(baseline_results, optimized_results):
                comparisons.append(VIRComparison(
                    prompt=baseline.prompt,
                    baseline=baseline,
                    optimized=optimized,
                    confidence_delta=round(
                        optimized.confidence_score - baseline.confidence_score, 4,
                    ),
                    drift_delta=round(
                        optimized.ncg_drift - baseline.ncg_drift, 4,
                    ),
                    grade_improved=self._grade_rank(optimized.grade) > self._grade_rank(baseline.grade),
                    collapse_fixed=(
                        baseline.silent_collapse and not optimized.silent_collapse
                    ),
                ))

            # Phase 4: Produce report
            return self._build_report(proposals, comparisons)

        finally:
            self._cleanup_sandbox()

    def validate_batch(self, batch: ProposalBatch) -> VIRReport:
        """Validate all proposals in a batch."""
        return self.validate(batch.proposals)

    # --- Report building ---

    def _build_report(
        self,
        proposals: list,
        comparisons: list,
    ) -> VIRReport:
        """Analyze comparisons and produce the VIR report."""
        # Compute aggregate improvement
        confidence_deltas = [c.confidence_delta for c in comparisons]
        drift_deltas = [c.drift_delta for c in comparisons]
        grades_improved = sum(1 for c in comparisons if c.grade_improved)
        collapses_fixed = sum(1 for c in comparisons if c.collapse_fixed)

        mean_confidence_delta = (
            sum(confidence_deltas) / len(confidence_deltas)
            if confidence_deltas else 0.0
        )
        mean_drift_delta = (
            sum(drift_deltas) / len(drift_deltas)
            if drift_deltas else 0.0
        )

        # Overall improvement: positive confidence + negative drift = good
        # Scale to -1..1 range
        overall = round(mean_confidence_delta - mean_drift_delta, 4)
        overall = max(-1.0, min(1.0, overall))

        # Recommendation logic
        if overall > 0.05:
            recommendation = "promote"
        elif overall < -0.05:
            recommendation = "reject"
        else:
            recommendation = "needs_review"

        # Summary
        summary_parts = [
            f"Validated {len(proposals)} proposal(s) across "
            f"{len(comparisons)} benchmark(s).",
        ]
        if mean_confidence_delta > 0:
            summary_parts.append(
                f"Mean confidence improved by {mean_confidence_delta:.4f}."
            )
        elif mean_confidence_delta < 0:
            summary_parts.append(
                f"Mean confidence decreased by {abs(mean_confidence_delta):.4f}."
            )
        if grades_improved:
            summary_parts.append(
                f"{grades_improved} benchmark(s) showed grade improvement."
            )
        if collapses_fixed:
            summary_parts.append(
                f"{collapses_fixed} silent collapse(s) fixed."
            )
        summary_parts.append(f"Recommendation: {recommendation}.")

        return VIRReport(
            vir_id=self._vir_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            proposals_tested=[p.proposal_id for p in proposals],
            isolation_tier="local_sandbox" if self._node == "local" else "compute_node",
            benchmark_count=len(comparisons),
            comparisons=comparisons,
            overall_improvement=overall,
            recommendation=recommendation,
            summary=" ".join(summary_parts),
            node_id=self._node,
        )

    @staticmethod
    def _grade_rank(grade: str) -> int:
        """Numeric rank for grade comparison. Higher = better."""
        ranks = {"suspicious": 0, "weak": 1, "acceptable": 2, "strong": 3}
        return ranks.get(grade, -1)


# --- Remote compute node support ---

@dataclass
class ComputeNode:
    """Registration of a remote compute node for MAGI_VIR validation."""
    node_id: str
    host: str
    port: int = 8000
    status: str = "available"   # "available", "busy", "offline"
    capabilities: list = field(default_factory=list)  # ["local_sandbox", "full_pipeline"]
    metadata: dict = field(default_factory=dict)


class ComputeNodeRegistry:
    """
    Registry of available compute nodes for distributed MAGI_VIR validation.

    In a multi-node Maestro deployment, different nodes can specialize
    in different validation tasks. The registry tracks which nodes are
    available and what they can do.
    """

    def __init__(self, registry_dir: str = None):
        self._dir = Path(registry_dir) if registry_dir else (
            _MAESTRO_ROOT / "data" / "compute_nodes"
        )
        self._dir.mkdir(parents=True, exist_ok=True)

    def register(self, node: ComputeNode) -> Path:
        """Register a compute node."""
        filepath = self._dir / f"{node.node_id}.json"
        filepath.write_text(json.dumps(asdict(node), indent=2))
        return filepath

    def unregister(self, node_id: str) -> bool:
        """Remove a compute node from the registry."""
        filepath = self._dir / f"{node_id}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def get(self, node_id: str) -> Optional[ComputeNode]:
        """Load a compute node by ID."""
        filepath = self._dir / f"{node_id}.json"
        if not filepath.exists():
            return None
        data = json.loads(filepath.read_text())
        return ComputeNode(**data)

    def list_available(self) -> list:
        """List all available compute nodes."""
        nodes = []
        for filepath in self._dir.glob("*.json"):
            try:
                data = json.loads(filepath.read_text())
                node = ComputeNode(**data)
                if node.status == "available":
                    nodes.append(node)
            except (json.JSONDecodeError, TypeError):
                continue
        return nodes

    def select_node(self, required_capabilities: list = None) -> Optional[ComputeNode]:
        """
        Select the best available compute node for a validation run.

        Prefers nodes with matching capabilities. Falls back to any
        available node.
        """
        available = self.list_available()
        if not available:
            return None

        if required_capabilities:
            matching = [
                n for n in available
                if all(cap in n.capabilities for cap in required_capabilities)
            ]
            if matching:
                return matching[0]

        return available[0]

    def update_status(self, node_id: str, status: str) -> bool:
        """Update a node's status."""
        node = self.get(node_id)
        if node is None:
            return False
        node.status = status
        self.register(node)
        return True
