"""
Tests for the code injection system:
  - RollbackLog — snapshot/restore
  - InjectionGuard — safety rails
  - CodeInjector — applying proposals
  - SelfImprovementEngine integration with auto-injection
"""

import json
import os
import shutil
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from maestro.rollback import RollbackLog, RollbackEntry
from maestro.injection_guard import (
    InjectionGuard, GuardConfig, _GRADE_RANK,
)
from maestro.applicator import CodeInjector, InjectionResult
from maestro.optimization import OptimizationProposal, ProposalBatch
from maestro.self_improve import SelfImprovementEngine, ImprovementCycle
from maestro.r2 import R2Engine
from maestro.session import SessionLogger
from maestro.dissent import DissentReport
from maestro.ncg.drift import DriftReport


# ======================================================================
# Helpers
# ======================================================================

def _make_proposal(
    proposal_id="prop-1",
    category="threshold",
    target_name="QUORUM_THRESHOLD",
    module_name="maestro.aggregator",
    current_value="0.66",
    proposed_value="0.71",
    change_type="parameter_update",
    file_path="maestro/aggregator.py",
    status="validated",
    priority="high",
):
    return OptimizationProposal(
        proposal_id=proposal_id,
        timestamp="2024-01-01T00:00:00Z",
        category=category,
        priority=priority,
        title="Test proposal",
        description="Test description",
        file_path=file_path,
        module_name=module_name,
        target_name=target_name,
        line_number=3,
        current_value=current_value,
        proposed_value=proposed_value,
        change_type=change_type,
        status=status,
    )


# ======================================================================
# RollbackLog Tests
# ======================================================================

class TestRollbackLog(unittest.TestCase):
    """Verify snapshot/restore mechanics."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.log = RollbackLog(rollback_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_snapshot_runtime(self):
        entry = self.log.snapshot_runtime(
            proposal_id="p1", cycle_id="c1",
            module_name="maestro.aggregator",
            target_name="QUORUM_THRESHOLD",
            original_value="0.66", new_value="0.71",
        )
        self.assertIsInstance(entry, RollbackEntry)
        self.assertEqual(entry.injection_type, "runtime")
        self.assertEqual(entry.original_value, "0.66")
        self.assertEqual(entry.status, "applied")

    def test_snapshot_persists_to_disk(self):
        self.log.snapshot_runtime(
            proposal_id="p1", cycle_id="c1",
            module_name="m", target_name="t",
            original_value="a", new_value="b",
        )
        # Reload from disk
        log2 = RollbackLog(rollback_dir=self._tmpdir)
        self.assertEqual(len(log2.get_active()), 1)

    def test_mark_rolled_back(self):
        entry = self.log.snapshot_runtime(
            proposal_id="p1", cycle_id="c1",
            module_name="m", target_name="t",
            original_value="a", new_value="b",
        )
        result = self.log.mark_rolled_back(entry.rollback_id)
        self.assertTrue(result)
        self.assertEqual(len(self.log.get_active()), 0)

    def test_mark_rolled_back_not_found(self):
        self.assertFalse(self.log.mark_rolled_back("nonexistent"))

    def test_mark_rolled_back_already_rolled_back(self):
        entry = self.log.snapshot_runtime(
            proposal_id="p1", cycle_id="c1",
            module_name="m", target_name="t",
            original_value="a", new_value="b",
        )
        self.log.mark_rolled_back(entry.rollback_id)
        # Second call should return False
        self.assertFalse(self.log.mark_rolled_back(entry.rollback_id))

    def test_get_by_cycle(self):
        self.log.snapshot_runtime(
            proposal_id="p1", cycle_id="c1",
            module_name="m", target_name="t1",
            original_value="a", new_value="b",
        )
        self.log.snapshot_runtime(
            proposal_id="p2", cycle_id="c1",
            module_name="m", target_name="t2",
            original_value="c", new_value="d",
        )
        self.log.snapshot_runtime(
            proposal_id="p3", cycle_id="c2",
            module_name="m", target_name="t3",
            original_value="e", new_value="f",
        )
        entries = self.log.get_by_cycle("c1")
        self.assertEqual(len(entries), 2)

    def test_get_active_by_cycle(self):
        e1 = self.log.snapshot_runtime(
            proposal_id="p1", cycle_id="c1",
            module_name="m", target_name="t1",
            original_value="a", new_value="b",
        )
        self.log.snapshot_runtime(
            proposal_id="p2", cycle_id="c1",
            module_name="m", target_name="t2",
            original_value="c", new_value="d",
        )
        self.log.mark_rolled_back(e1.rollback_id)
        active = self.log.get_active_by_cycle("c1")
        self.assertEqual(len(active), 1)

    def test_snapshot_source_creates_backup(self):
        # Create a fake source file
        src = Path(self._tmpdir) / "fake.py"
        src.write_text("QUORUM_THRESHOLD = 0.66\n")

        entry = self.log.snapshot_source(
            proposal_id="p1", cycle_id="c1",
            module_name="maestro.aggregator",
            target_name="QUORUM_THRESHOLD",
            file_path=str(src),
            original_value="0.66", new_value="0.71",
        )
        self.assertTrue(Path(entry.backup_path).exists())
        backup_content = Path(entry.backup_path).read_text()
        self.assertIn("0.66", backup_content)

    def test_count_active(self):
        self.assertEqual(self.log.count_active(), 0)
        self.log.snapshot_runtime(
            proposal_id="p1", cycle_id="c1",
            module_name="m", target_name="t",
            original_value="a", new_value="b",
        )
        self.assertEqual(self.log.count_active(), 1)

    def test_list_all(self):
        for i in range(3):
            self.log.snapshot_runtime(
                proposal_id=f"p{i}", cycle_id="c1",
                module_name="m", target_name=f"t{i}",
                original_value="a", new_value="b",
            )
        entries = self.log.list_all()
        self.assertEqual(len(entries), 3)


# ======================================================================
# InjectionGuard Tests
# ======================================================================

class TestInjectionGuard(unittest.TestCase):
    """Verify safety rails for the injection system."""

    def test_is_enabled_default(self):
        guard = InjectionGuard()
        # Should be disabled by default
        os.environ.pop("MAESTRO_AUTO_INJECT", None)
        self.assertFalse(guard.is_enabled())

    def test_is_enabled_via_env(self):
        guard = InjectionGuard()
        os.environ["MAESTRO_AUTO_INJECT"] = "true"
        try:
            self.assertTrue(guard.is_enabled())
        finally:
            os.environ.pop("MAESTRO_AUTO_INJECT", None)

    def test_is_enabled_via_config(self):
        config = GuardConfig(auto_inject_enabled=True)
        guard = InjectionGuard(config=config)
        self.assertTrue(guard.is_enabled())

    def test_injectable_threshold_allowed(self):
        guard = InjectionGuard()
        proposal = _make_proposal(category="threshold")
        allowed, reason = guard.is_injectable(proposal)
        self.assertTrue(allowed)

    def test_injectable_architecture_blocked(self):
        guard = InjectionGuard()
        proposal = _make_proposal(category="architecture")
        allowed, reason = guard.is_injectable(proposal)
        self.assertFalse(allowed)
        self.assertIn("blocked", reason)

    def test_injectable_unknown_category_blocked(self):
        guard = InjectionGuard()
        proposal = _make_proposal(category="unknown_cat")
        allowed, reason = guard.is_injectable(proposal)
        self.assertFalse(allowed)

    def test_injectable_rejected_status(self):
        guard = InjectionGuard()
        proposal = _make_proposal(status="rejected")
        allowed, reason = guard.is_injectable(proposal)
        self.assertFalse(allowed)

    def test_check_bounds_within(self):
        guard = InjectionGuard()
        proposal = _make_proposal(
            target_name="QUORUM_THRESHOLD",
            proposed_value="0.71",
            change_type="parameter_update",
        )
        self.assertTrue(guard.check_bounds(proposal))

    def test_check_bounds_out_of_range(self):
        guard = InjectionGuard()
        proposal = _make_proposal(
            target_name="QUORUM_THRESHOLD",
            proposed_value="0.99",  # exceeds max of 0.9
            change_type="parameter_update",
        )
        self.assertFalse(guard.check_bounds(proposal))

    def test_check_bounds_non_numeric_passes(self):
        guard = InjectionGuard()
        proposal = _make_proposal(
            change_type="config_change",
            proposed_value="gpt-4",
        )
        self.assertTrue(guard.check_bounds(proposal))

    def test_rate_limit_allows(self):
        guard = InjectionGuard()
        self.assertTrue(guard.check_rate_limit())

    def test_rate_limit_blocks(self):
        config = GuardConfig(max_injections_per_hour=2)
        guard = InjectionGuard(config=config)
        guard.record_injection()
        guard.record_injection()
        self.assertFalse(guard.check_rate_limit())

    def test_smoke_test_runs(self):
        guard = InjectionGuard()
        passed, grade = guard.smoke_test()
        self.assertIsInstance(passed, bool)
        self.assertIn(grade, _GRADE_RANK)

    def test_grade_rank_ordering(self):
        self.assertGreater(_GRADE_RANK["strong"], _GRADE_RANK["weak"])
        self.assertGreater(_GRADE_RANK["acceptable"], _GRADE_RANK["suspicious"])


# ======================================================================
# CodeInjector Tests
# ======================================================================

class TestCodeInjector(unittest.TestCase):
    """Verify the three injection paths and rollback."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._rollback_dir = tempfile.mkdtemp()
        self.rollback_log = RollbackLog(rollback_dir=self._rollback_dir)
        self.guard = InjectionGuard(config=GuardConfig(
            auto_inject_enabled=True,
            max_injections_per_hour=20,
        ))
        self.injector = CodeInjector(
            guard=self.guard,
            rollback_log=self.rollback_log,
        )

        # Save original threshold to restore
        import maestro.aggregator as agg
        self._original_quorum = agg.QUORUM_THRESHOLD
        self._original_similarity = agg.SIMILARITY_THRESHOLD

    def tearDown(self):
        import maestro.aggregator as agg
        agg.QUORUM_THRESHOLD = self._original_quorum
        agg.SIMILARITY_THRESHOLD = self._original_similarity
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        shutil.rmtree(self._rollback_dir, ignore_errors=True)

    def test_runtime_injection_applies(self):
        """Runtime injection should change the module variable."""
        import maestro.aggregator as agg
        proposal = _make_proposal(
            proposed_value="0.71",
            change_type="parameter_update",
        )
        result = self.injector.apply(proposal, cycle_id="test-cycle")
        self.assertTrue(result.applied)
        self.assertEqual(result.injection_type, "runtime")
        self.assertAlmostEqual(agg.QUORUM_THRESHOLD, 0.71)

    def test_runtime_injection_rollback(self):
        """Rolling back should restore the original value."""
        import maestro.aggregator as agg
        original = agg.QUORUM_THRESHOLD

        proposal = _make_proposal(proposed_value="0.75")
        result = self.injector.apply(proposal, cycle_id="test-cycle")
        self.assertAlmostEqual(agg.QUORUM_THRESHOLD, 0.75)

        success = self.injector.rollback(result.rollback_id)
        self.assertTrue(success)
        self.assertAlmostEqual(agg.QUORUM_THRESHOLD, original)

    def test_dry_run_does_not_mutate(self):
        """Dry run should validate but not apply."""
        import maestro.aggregator as agg
        original = agg.QUORUM_THRESHOLD

        proposal = _make_proposal(proposed_value="0.80")
        result = self.injector.apply(proposal, cycle_id="test", dry_run=True)
        self.assertFalse(result.applied)
        self.assertEqual(result.error, "dry_run")
        self.assertAlmostEqual(agg.QUORUM_THRESHOLD, original)

    def test_blocked_category_skipped(self):
        """Architecture proposals should be skipped."""
        proposal = _make_proposal(category="architecture")
        result = self.injector.apply(proposal, cycle_id="test")
        self.assertFalse(result.applied)
        self.assertEqual(result.injection_type, "skipped")

    def test_rate_limit_blocks_injection(self):
        """Exceeding rate limit should skip injection."""
        config = GuardConfig(
            auto_inject_enabled=True,
            max_injections_per_hour=1,
        )
        guard = InjectionGuard(config=config)
        injector = CodeInjector(guard=guard, rollback_log=self.rollback_log)

        p1 = _make_proposal(proposal_id="p1", proposed_value="0.71")
        r1 = injector.apply(p1, cycle_id="test")
        self.assertTrue(r1.applied)

        p2 = _make_proposal(proposal_id="p2", proposed_value="0.72")
        r2 = injector.apply(p2, cycle_id="test")
        self.assertFalse(r2.applied)
        self.assertIn("Rate limit", r2.error)

    def test_apply_batch(self):
        """Batch application should process multiple proposals."""
        proposals = [
            _make_proposal(
                proposal_id="p1",
                target_name="QUORUM_THRESHOLD",
                proposed_value="0.71",
            ),
            _make_proposal(
                proposal_id="p2",
                target_name="SIMILARITY_THRESHOLD",
                proposed_value="0.55",
            ),
        ]
        results = self.injector.apply_batch(proposals, cycle_id="test")
        self.assertEqual(len(results), 2)
        applied = [r for r in results if r.applied]
        self.assertEqual(len(applied), 2)

    def test_rollback_cycle(self):
        """rollback_cycle should undo all injections from a cycle."""
        import maestro.aggregator as agg
        orig_q = agg.QUORUM_THRESHOLD
        orig_s = agg.SIMILARITY_THRESHOLD

        proposals = [
            _make_proposal(
                proposal_id="p1",
                target_name="QUORUM_THRESHOLD",
                proposed_value="0.71",
            ),
            _make_proposal(
                proposal_id="p2",
                target_name="SIMILARITY_THRESHOLD",
                proposed_value="0.55",
            ),
        ]
        self.injector.apply_batch(proposals, cycle_id="cycle-1")

        results = self.injector.rollback_cycle("cycle-1")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(ok for _, ok in results))
        self.assertAlmostEqual(agg.QUORUM_THRESHOLD, orig_q)
        self.assertAlmostEqual(agg.SIMILARITY_THRESHOLD, orig_s)

    def test_rollback_nonexistent(self):
        """Rolling back a nonexistent ID should return False."""
        self.assertFalse(self.injector.rollback("nonexistent"))

    def test_config_injection(self):
        """Config change should write to runtime_config.json."""
        # Use a temp dir to avoid polluting repo data/
        import maestro.applicator as app_mod
        original_root = app_mod._MAESTRO_ROOT
        app_mod._MAESTRO_ROOT = Path(self._tmpdir)
        (Path(self._tmpdir) / "data").mkdir(parents=True, exist_ok=True)

        try:
            proposal = _make_proposal(
                category="agent_config",
                target_name="temperature",
                proposed_value="temperature raise by 0.1",
                change_type="config_change",
                module_name="maestro.agents",
            )
            result = self.injector.apply(proposal, cycle_id="test")
            self.assertTrue(result.applied)
            self.assertEqual(result.injection_type, "config")

            config_path = Path(self._tmpdir) / "data" / "runtime_config.json"
            self.assertTrue(config_path.exists())
            config = json.loads(config_path.read_text())
            self.assertIn("temperature", config)
        finally:
            app_mod._MAESTRO_ROOT = original_root

    def test_out_of_bounds_proposal_skipped(self):
        """Proposals with out-of-bounds values should be rejected."""
        proposal = _make_proposal(
            target_name="QUORUM_THRESHOLD",
            proposed_value="0.99",  # above max 0.9
        )
        result = self.injector.apply(proposal, cycle_id="test")
        self.assertFalse(result.applied)
        self.assertIn("bounds", result.error)

    def test_injection_updates_proposal_status(self):
        """After injection, proposal status should be 'promoted'."""
        proposal = _make_proposal(proposed_value="0.71")
        self.injector.apply(proposal, cycle_id="test")
        self.assertEqual(proposal.status, "promoted")


# ======================================================================
# Integration: SelfImprovementEngine with auto-injection
# ======================================================================

class TestAutoInjectionIntegration(unittest.TestCase):
    """End-to-end test of auto-injection through the improvement cycle."""

    def setUp(self):
        self._r2_dir = tempfile.mkdtemp()
        self._session_dir = tempfile.mkdtemp()
        self._improve_dir = tempfile.mkdtemp()
        self._tmpdir_session = tempfile.mkdtemp()
        self._tmpdir_r2 = tempfile.mkdtemp()

        self.r2 = R2Engine(ledger_dir=self._r2_dir)
        self.session_logger = SessionLogger(storage_dir=self._session_dir)

        # Patch default dirs for isolation
        import maestro.session as session_mod
        import maestro.r2 as r2_mod
        self._original_session_dir = session_mod._DEFAULT_DIR
        self._original_r2_dir = r2_mod._DEFAULT_LEDGER_DIR
        session_mod._DEFAULT_DIR = Path(self._tmpdir_session)
        r2_mod._DEFAULT_LEDGER_DIR = Path(self._tmpdir_r2)

        # Save original thresholds
        import maestro.aggregator as agg
        self._orig_quorum = agg.QUORUM_THRESHOLD
        self._orig_similarity = agg.SIMILARITY_THRESHOLD

    def tearDown(self):
        import maestro.session as session_mod
        import maestro.r2 as r2_mod
        session_mod._DEFAULT_DIR = self._original_session_dir
        r2_mod._DEFAULT_LEDGER_DIR = self._original_r2_dir

        import maestro.aggregator as agg
        agg.QUORUM_THRESHOLD = self._orig_quorum
        agg.SIMILARITY_THRESHOLD = self._orig_similarity

        os.environ.pop("MAESTRO_AUTO_INJECT", None)

        for d in (self._r2_dir, self._session_dir, self._improve_dir,
                  self._tmpdir_session, self._tmpdir_r2):
            shutil.rmtree(d, ignore_errors=True)

    def _populate_ledger(self, count=5, collapse=True):
        for i in range(count):
            dissent = DissentReport(
                prompt=f"prompt {i}",
                internal_agreement=0.95 if collapse else 0.8,
                pairwise=[],
                agent_profiles=[],
                outlier_agents=[],
                dissent_level="low",
                agent_count=3,
            )
            drift = DriftReport(
                prompt=f"prompt {i}",
                ncg_content="baseline",
                ncg_model="mock",
                agent_signals=[],
                mean_semantic_distance=0.6 if collapse else 0.2,
                max_semantic_distance=0.7 if collapse else 0.3,
                silent_collapse_detected=collapse,
                compression_alert=False,
            )
            score = self.r2.score_session(dissent, drift, quorum_confidence="High")
            signals = self.r2.detect_signals(score, dissent, drift)
            self.r2.index(
                session_id=f"sess-{i}",
                prompt=f"prompt {i}",
                consensus="answer",
                agents_agreed=["Sol", "Aria", "Prism"],
                score=score,
                improvement_signals=signals,
                dissent_report=dissent,
                drift_report=drift,
            )

    def test_auto_inject_disabled_no_injections(self):
        """When auto-inject is off, cycle should not inject."""
        os.environ.pop("MAESTRO_AUTO_INJECT", None)
        self._populate_ledger(count=5, collapse=True)

        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test prompt"],
        )
        cycle = engine.run_cycle()
        self.assertFalse(cycle.auto_injected)
        self.assertEqual(len(cycle.injections), 0)

    def test_auto_inject_enabled_applies_proposals(self):
        """When auto-inject is on and VIR promotes, proposals are injected."""
        os.environ["MAESTRO_AUTO_INJECT"] = "true"
        self._populate_ledger(count=5, collapse=True)

        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test prompt"],
        )
        cycle = engine.run_cycle()

        # The cycle should have completed
        self.assertEqual(cycle.phase, "complete")

        # If proposals were generated and promoted, injection should have
        # been attempted
        if cycle.outcome == "promoted" and cycle.proposal_count > 0:
            self.assertTrue(cycle.auto_injected)
            self.assertGreater(len(cycle.injections), 0)

    def test_improvement_cycle_fields(self):
        """ImprovementCycle should have all new injection fields."""
        cycle = ImprovementCycle(
            cycle_id="test",
            timestamp="2024-01-01",
            phase="complete",
        )
        self.assertFalse(cycle.auto_injected)
        self.assertEqual(cycle.injections, [])
        self.assertFalse(cycle.rollback_triggered)
        self.assertIsNone(cycle.smoke_test_grade)

    def test_inject_cycle_manual(self):
        """inject_cycle should apply proposals from a recorded cycle."""
        os.environ.pop("MAESTRO_AUTO_INJECT", None)
        self._populate_ledger(count=5, collapse=True)

        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test prompt"],
        )
        cycle = engine.run_cycle()

        if cycle.outcome in ("promoted", "needs_review") and cycle.proposal_count > 0:
            result = engine.inject_cycle(cycle.cycle_id)
            self.assertIn("injections", result)
            self.assertIn("applied_count", result)

    def test_inject_cycle_not_found(self):
        """inject_cycle with bad ID should return error."""
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
        )
        result = engine.inject_cycle("nonexistent-id")
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main()
