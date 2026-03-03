"""
Self-Improvement Orchestrator — The complete rapid recursion loop.

This is the central coordinator for Maestro's self-improvement capability.
It ties together all the components:

  1. MAGI analysis → identifies cross-session patterns
  2. R2 signal collection → gathers improvement signals from the ledger
  3. Code introspection → maps signals to source code locations
  4. Optimization proposals → generates concrete change proposals
  5. MAGI_VIR validation → tests proposals in isolated sandbox
  6. Promotion/rejection → records results and updates proposal status
  7. Code injection → applies validated proposals to the running system
     (opt-in, guarded, reversible)

The loop can run in two modes:
  - On-demand: triggered by a human or API call
  - Continuous: runs after every N sessions (configurable)

When auto-injection is enabled (MAESTRO_AUTO_INJECT=true), validated
proposals are applied to the running system after VIR validation with
a post-injection smoke test.  If the smoke test fails, the entire
batch is automatically rolled back.  When disabled (the default), the
system behaves exactly as before — proposals are recorded but never
applied.

This is the "rapid recursion" that the whitepaper describes: the system
observes its own behavior, identifies where it can improve, tests those
improvements in isolation, and applies the changes — closing the loop.
"""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from maestro.magi import Magi, MagiReport, _run_introspection_pipeline
from maestro.r2 import R2Engine
from maestro.session import SessionLogger
from maestro.magi_vir import MagiVIR, VIRReport, ComputeNodeRegistry


_DEFAULT_IMPROVEMENT_DIR = Path(__file__).resolve().parent.parent / "data" / "improvements"


@dataclass
class ImprovementCycle:
    """Complete record of a single self-improvement cycle."""
    cycle_id: str
    timestamp: str
    phase: str                  # "analysis", "introspection", "proposal",
                                # "validation", "complete", "failed"

    # Phase outputs
    magi_report: Optional[dict] = None
    introspection_summary: Optional[str] = None
    proposal_count: int = 0
    proposals: list = field(default_factory=list)    # serialized proposals
    vir_report: Optional[dict] = None

    # Outcome
    outcome: str = "pending"    # "pending", "promoted", "rejected",
                                # "needs_review", "no_proposals"
    promoted_proposals: list = field(default_factory=list)
    rejected_proposals: list = field(default_factory=list)

    # Injection (Phase 7)
    auto_injected: bool = False
    injections: list = field(default_factory=list)   # list of InjectionResult dicts
    rollback_triggered: bool = False
    smoke_test_grade: Optional[str] = None

    # Metadata
    compute_node: str = "local"
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)


class SelfImprovementEngine:
    """
    Orchestrates the complete self-improvement loop.

    This is the top-level coordinator. Call `run_cycle()` to execute
    one full iteration of the rapid recursion loop:

      MAGI → Introspect → Propose → Validate (VIR) → Promote/Reject

    The engine is stateless between cycles. All persistence is handled
    by the underlying components (R2 ledger, session logger, improvement
    log). Each cycle is a self-contained transaction.
    """

    def __init__(
        self,
        r2: R2Engine = None,
        session_logger: SessionLogger = None,
        compute_node: str = "local",
        improvement_dir: str = None,
        benchmark_prompts: list = None,
    ):
        self._r2 = r2 or R2Engine()
        self._sessions = session_logger or SessionLogger()
        self._compute_node = compute_node
        self._improvement_dir = (
            Path(improvement_dir) if improvement_dir
            else _DEFAULT_IMPROVEMENT_DIR
        )
        self._improvement_dir.mkdir(parents=True, exist_ok=True)
        self._benchmark_prompts = benchmark_prompts

        # Components
        self._magi = Magi(r2=self._r2, session_logger=self._sessions)

    def run_cycle(self) -> ImprovementCycle:
        """
        Execute one complete self-improvement cycle.

        Returns an ImprovementCycle recording every phase of the loop
        and the final outcome.
        """
        import time
        start = time.monotonic()

        cycle = ImprovementCycle(
            cycle_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            phase="analysis",
            compute_node=self._compute_node,
        )

        try:
            # Phase 1: MAGI cross-session analysis
            magi_report = self._magi.analyze()
            cycle.magi_report = self._serialize_magi_report(magi_report)
            cycle.phase = "introspection"

            # Phases 2-3: Code introspection + proposal generation
            # Uses shared pipeline to avoid duplication with Magi.analyze_with_introspection()
            ledger_entries = self._r2.load_recent_entries(50)
            introspection, batch = _run_introspection_pipeline(
                r2=self._r2,
                ledger_entries=ledger_entries,
                magi_recommendations=magi_report.recommendations,
            )
            cycle.introspection_summary = introspection.summary
            cycle.phase = "proposal"
            cycle.proposal_count = batch.total_proposals
            cycle.proposals = [asdict(p) for p in batch.proposals]

            if batch.total_proposals == 0:
                cycle.phase = "complete"
                cycle.outcome = "no_proposals"
                cycle.duration_ms = int((time.monotonic() - start) * 1000)
                self._persist_cycle(cycle)
                return cycle

            # Phase 4: Validate in MAGI_VIR sandbox
            cycle.phase = "validation"
            vir = MagiVIR(
                compute_node=self._compute_node,
                benchmark_prompts=self._benchmark_prompts,
            )
            vir_report = vir.validate_batch(batch)
            cycle.vir_report = self._serialize_vir_report(vir_report)

            # Phase 5: Promote or reject based on VIR results
            cycle.phase = "complete"
            if vir_report.recommendation == "promote":
                cycle.outcome = "promoted"
                cycle.promoted_proposals = vir_report.proposals_tested
            elif vir_report.recommendation == "reject":
                cycle.outcome = "rejected"
                cycle.rejected_proposals = vir_report.proposals_tested
            else:
                cycle.outcome = "needs_review"

            # Update proposal statuses
            for proposal in batch.proposals:
                if vir_report.recommendation == "promote":
                    proposal.status = "validated"
                elif vir_report.recommendation == "reject":
                    proposal.status = "rejected"
                else:
                    proposal.status = "proposed"
                proposal.validation_result = {
                    "vir_id": vir_report.vir_id,
                    "overall_improvement": vir_report.overall_improvement,
                    "recommendation": vir_report.recommendation,
                }

            # Phase 6: Code injection (opt-in)
            if vir_report.recommendation == "promote":
                self._try_auto_inject(cycle, batch)

        except Exception as e:
            cycle.phase = "failed"
            cycle.outcome = "failed"
            cycle.metadata["error"] = str(e)
            cycle.metadata["error_type"] = type(e).__name__

        cycle.duration_ms = int((time.monotonic() - start) * 1000)
        self._persist_cycle(cycle)
        return cycle

    def _try_auto_inject(self, cycle: ImprovementCycle, batch):
        """
        Phase 6: If auto-injection is enabled and VIR recommends
        promotion, apply validated proposals to the running system.

        Runs a smoke test after injection and auto-rolls-back on
        degradation.
        """
        from maestro.applicator import CodeInjector
        from maestro.injection_guard import InjectionGuard

        guard = InjectionGuard()
        if not guard.is_enabled():
            return  # auto-inject not enabled — nothing to do

        cycle.phase = "injection"
        injector = CodeInjector(guard=guard)

        results = injector.apply_batch(
            batch.proposals, cycle_id=cycle.cycle_id,
        )
        cycle.auto_injected = True
        cycle.injections = [
            {
                "proposal_id": r.proposal_id,
                "applied": r.applied,
                "injection_type": r.injection_type,
                "rollback_id": r.rollback_id,
                "error": r.error,
            }
            for r in results
        ]

        any_applied = any(r.applied for r in results)
        if not any_applied:
            cycle.phase = "complete"
            return

        # Smoke test
        passed, grade = guard.smoke_test()
        cycle.smoke_test_grade = grade

        if not passed:
            # Auto-rollback the entire cycle
            rollback_results = injector.rollback_cycle(cycle.cycle_id)
            cycle.rollback_triggered = True
            cycle.metadata["rollback_reason"] = (
                f"Smoke test failed: grade '{grade}' below minimum"
            )
            cycle.metadata["rollback_results"] = [
                {"rollback_id": rid, "success": ok}
                for rid, ok in rollback_results
            ]

        cycle.phase = "complete"

    def inject_cycle(self, cycle_id: str) -> dict:
        """
        Manually inject proposals from a previously validated cycle.

        This is the human-in-the-loop path: review a cycle's proposals
        in the UI, then trigger injection via API.
        """
        from maestro.applicator import CodeInjector
        from maestro.injection_guard import InjectionGuard
        from maestro.optimization import OptimizationProposal

        cycle_data = self.load_cycle(cycle_id)
        if cycle_data is None:
            return {"error": "Cycle not found"}

        if cycle_data.get("outcome") not in ("promoted", "needs_review"):
            return {"error": f"Cycle outcome is '{cycle_data.get('outcome')}', not injectable"}

        proposals = []
        for p in cycle_data.get("proposals", []):
            proposals.append(OptimizationProposal(**{
                k: v for k, v in p.items()
                if k in OptimizationProposal.__dataclass_fields__
            }))

        guard = InjectionGuard()
        injector = CodeInjector(guard=guard)
        results = injector.apply_batch(proposals, cycle_id=cycle_id)

        return {
            "cycle_id": cycle_id,
            "injections": [
                {
                    "proposal_id": r.proposal_id,
                    "applied": r.applied,
                    "injection_type": r.injection_type,
                    "rollback_id": r.rollback_id,
                    "error": r.error,
                }
                for r in results
            ],
            "applied_count": sum(1 for r in results if r.applied),
            "skipped_count": sum(1 for r in results if not r.applied),
        }

    def run_analysis_only(self) -> dict:
        """
        Run just the analysis + introspection phases without validation.
        Useful for inspection and planning.
        """
        magi_report = self._magi.analyze()
        ledger_entries = self._r2.load_recent_entries(50)
        introspection, batch = _run_introspection_pipeline(
            r2=self._r2,
            ledger_entries=ledger_entries,
            magi_recommendations=magi_report.recommendations,
        )

        return {
            "magi_report": self._serialize_magi_report(magi_report),
            "introspection_summary": introspection.summary,
            "code_targets": len(introspection.code_targets),
            "complexity_hotspots": introspection.complexity_hotspots[:5],
            "proposals": [asdict(p) for p in batch.proposals],
            "proposal_count": batch.total_proposals,
            "batch_summary": batch.summary,
        }

    # --- Cycle history ---

    def list_cycles(self, limit: int = 20) -> list:
        """List recent improvement cycles, most recent first."""
        files = sorted(
            self._improvement_dir.glob("cycle_*.json"),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        cycles = []
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text())
                cycles.append({
                    "cycle_id": data["cycle_id"],
                    "timestamp": data["timestamp"],
                    "phase": data["phase"],
                    "outcome": data["outcome"],
                    "proposal_count": data["proposal_count"],
                    "duration_ms": data.get("duration_ms", 0),
                    "compute_node": data.get("compute_node", "local"),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return cycles

    def load_cycle(self, cycle_id: str) -> Optional[dict]:
        """Load a complete cycle record."""
        filepath = self._improvement_dir / f"cycle_{cycle_id}.json"
        if not filepath.exists():
            return None
        return json.loads(filepath.read_text())

    def count_cycles(self) -> int:
        """Total number of recorded cycles."""
        return len(list(self._improvement_dir.glob("cycle_*.json")))

    # --- Persistence ---

    def _persist_cycle(self, cycle: ImprovementCycle):
        """Write cycle record to the improvement log."""
        filepath = self._improvement_dir / f"cycle_{cycle.cycle_id}.json"
        filepath.write_text(json.dumps(asdict(cycle), indent=2, default=str))

    @staticmethod
    def _serialize_magi_report(report: MagiReport) -> dict:
        """Serialize a MagiReport for storage."""
        return {
            "sessions_analyzed": report.sessions_analyzed,
            "ledger_entries_analyzed": report.ledger_entries_analyzed,
            "confidence_trend": report.confidence_trend,
            "mean_confidence": report.mean_confidence,
            "grade_distribution": report.grade_distribution,
            "agent_health": report.agent_health,
            "collapse_frequency": report.collapse_frequency,
            "recurring_signals": report.recurring_signals,
            "recommendation_count": len(report.recommendations),
            "recommendations": [asdict(r) for r in report.recommendations],
        }

    @staticmethod
    def _serialize_vir_report(report: VIRReport) -> dict:
        """Serialize a VIRReport for storage."""
        return {
            "vir_id": report.vir_id,
            "isolation_tier": report.isolation_tier,
            "benchmark_count": report.benchmark_count,
            "overall_improvement": report.overall_improvement,
            "recommendation": report.recommendation,
            "summary": report.summary,
            "node_id": report.node_id,
            "comparisons": [
                {
                    "prompt": c.prompt[:100],
                    "confidence_delta": c.confidence_delta,
                    "drift_delta": c.drift_delta,
                    "grade_improved": c.grade_improved,
                    "collapse_fixed": c.collapse_fixed,
                    "baseline_grade": c.baseline.grade,
                    "optimized_grade": c.optimized.grade,
                }
                for c in report.comparisons
            ],
        }
