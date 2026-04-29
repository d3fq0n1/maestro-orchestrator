"""
Context Router — composes per-agent context bundles from the three tiers.

See docs/architecture/router-distance.md.

The Router runs inside the existing ``pre_orchestration`` hook
(see context-tiers.md §Per-agent pre-fetch hook). It assembles a
trust-annotated bundle per agent, writes an R2 pre-admit entry,
gates through AdmissionGuard, and attaches a rendered preamble the
orchestrator prepends to the prompt string before ``agent.fetch()``.

This package is a scaffold. Nothing is wired into the runtime.
"""

from maestro.router.benchmark import (
    BenchmarkCandidate,
    BenchmarkDataset,
    BenchmarkExample,
    BenchmarkQuery,
    BenchmarkResult,
    CandidateOutcome,
    ExampleOutcome,
    RankingMetrics,
    TierMetrics,
)
from maestro.router.benchmark_runner import BenchmarkRunner
from maestro.router.conformity import (
    ConformitySession,
    ConformityWindow,
    conformity_score,
    select_dissenter,
)
from maestro.router.distance import (
    AdmissionCriterion,
    AdmittedClaim,
    BundleRequest,
    ContextBundle,
    ContextRouter,
    DistanceMetric,
    DistanceWeights,
    Tier,
)

__all__ = [
    "AdmissionCriterion",
    "AdmittedClaim",
    "BenchmarkCandidate",
    "BenchmarkDataset",
    "BenchmarkExample",
    "BenchmarkQuery",
    "BenchmarkResult",
    "BenchmarkRunner",
    "BundleRequest",
    "CandidateOutcome",
    "ConformitySession",
    "ConformityWindow",
    "ContextBundle",
    "ContextRouter",
    "DistanceMetric",
    "DistanceWeights",
    "ExampleOutcome",
    "RankingMetrics",
    "Tier",
    "TierMetrics",
    "conformity_score",
    "select_dissenter",
]
