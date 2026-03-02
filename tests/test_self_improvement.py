"""
Tests for the self-improvement pipeline:
  - Code introspection engine
  - Optimization proposal system
  - MAGI_VIR virtual instance runtime
  - Self-improvement orchestrator
  - MAGI code-optimization-aware analysis
"""

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from dataclasses import asdict

from maestro.introspect import (
    CodeIntrospector, CodeTarget, IntrospectionReport,
)
from maestro.optimization import (
    OptimizationEngine, OptimizationProposal, ProposalBatch,
)
from maestro.magi_vir import (
    MagiVIR, VIRReport, BenchmarkResult, VIRComparison,
    ComputeNodeRegistry, ComputeNode,
)
from maestro.self_improve import (
    SelfImprovementEngine, ImprovementCycle,
)
from maestro.r2 import R2Engine, R2Score, ImprovementSignal
from maestro.session import SessionLogger
from maestro.dissent import DissentReport
from maestro.ncg.drift import DriftReport
from maestro.magi import Magi, MagiReport, Recommendation


# ===========================================================================
# Code Introspection Tests
# ===========================================================================

class TestCodeIntrospector(unittest.TestCase):
    """Verify the code introspection engine can analyze Maestro's source."""

    def setUp(self):
        self.introspector = CodeIntrospector()

    def test_discover_source_files(self):
        """Should find all Python files in the maestro package."""
        files = self.introspector._discover_source_files()
        self.assertGreater(len(files), 0)
        # Should include known files
        filenames = [f.name for f in files]
        self.assertIn("orchestrator.py", filenames)
        self.assertIn("magi.py", filenames)
        self.assertIn("r2.py", filenames)

    def test_analyze_source(self):
        """Static analysis should find functions and classes."""
        result = self.introspector.analyze_source()
        self.assertGreater(result["total_functions"], 0)
        self.assertGreater(result["total_classes"], 0)
        self.assertGreater(len(result["files"]), 0)

    def test_complexity_hotspots(self):
        """Should identify functions with high complexity."""
        result = self.introspector.analyze_source()
        # There should be at least some hotspots
        # (the codebase has functions with branching logic)
        self.assertIsInstance(result["complexity_hotspots"], list)
        for hotspot in result["complexity_hotspots"]:
            self.assertIn("function", hotspot)
            self.assertIn("file", hotspot)
            self.assertIn("complexity", hotspot)
            self.assertGreater(hotspot["complexity"], 0.3)

    def test_map_signals_to_code_suspicious_consensus(self):
        """Should map suspicious_consensus signal to relevant code targets."""
        signals = [
            {
                "signal_type": "suspicious_consensus",
                "affected_agents": [],
                "data": {"ncg_drift": 0.6},
            },
        ]
        mappings = self.introspector.map_signals_to_code(signals)
        self.assertIn("suspicious_consensus", mappings)
        targets = mappings["suspicious_consensus"]
        self.assertGreater(len(targets), 0)
        for target in targets:
            self.assertIsInstance(target, CodeTarget)
            self.assertIn("suspicious_consensus", target.linked_signals)

    def test_map_signals_to_code_persistent_outlier(self):
        """Should map persistent_outlier to agent config targets."""
        signals = [
            {
                "signal_type": "persistent_outlier",
                "affected_agents": ["Prism"],
                "data": {"agreement": 0.5},
            },
        ]
        mappings = self.introspector.map_signals_to_code(signals)
        self.assertIn("persistent_outlier", mappings)

    def test_map_signals_unknown_type(self):
        """Unknown signal types should produce no mappings."""
        signals = [{"signal_type": "nonexistent_signal"}]
        mappings = self.introspector.map_signals_to_code(signals)
        self.assertNotIn("nonexistent_signal", mappings)

    def test_analyze_token_patterns_empty(self):
        """Empty ledger should produce no token targets."""
        targets = self.introspector.analyze_token_patterns([])
        self.assertEqual(targets, [])

    def test_analyze_token_patterns_with_compression(self):
        """Entries with compression should produce token targets."""
        entries = [
            {
                "entry_id": "test-1",
                "prompt": "test prompt",
                "score": {"compression_alert": True},
                "dissent_summary": {"internal_agreement": 0.9},
                "improvement_signals": [],
            },
        ]
        targets = self.introspector.analyze_token_patterns(entries)
        self.assertIsInstance(targets, list)

    def test_full_introspection(self):
        """Full introspect() should produce a complete IntrospectionReport."""
        signals = [
            {
                "signal_type": "suspicious_consensus",
                "affected_agents": [],
                "data": {},
            },
        ]
        report = self.introspector.introspect(improvement_signals=signals)
        self.assertIsInstance(report, IntrospectionReport)
        self.assertGreater(report.files_analyzed, 0)
        self.assertGreater(report.total_functions, 0)
        self.assertIsInstance(report.summary, str)
        self.assertGreater(len(report.summary), 0)

    def test_introspect_no_signals(self):
        """Introspection with no signals should still analyze source."""
        report = self.introspector.introspect()
        self.assertIsInstance(report, IntrospectionReport)
        self.assertGreater(report.files_analyzed, 0)
        self.assertEqual(len(report.signal_mappings), 0)

    def test_code_target_deduplication(self):
        """Duplicate code targets should be deduplicated."""
        signals = [
            {"signal_type": "suspicious_consensus", "affected_agents": [], "data": {}},
            {"signal_type": "suspicious_consensus", "affected_agents": [], "data": {}},
        ]
        report = self.introspector.introspect(improvement_signals=signals)
        # Targets should be deduplicated by (file_path, target_name)
        target_keys = [(t.file_path, t.target_name) for t in report.code_targets]
        self.assertEqual(len(target_keys), len(set(target_keys)))


# ===========================================================================
# Optimization Engine Tests
# ===========================================================================

class TestOptimizationEngine(unittest.TestCase):
    """Verify optimization proposal generation from introspection results."""

    def setUp(self):
        self.optimizer = OptimizationEngine()

    def _make_introspection_report(self, code_targets=None, token_targets=None,
                                    hotspots=None):
        return IntrospectionReport(
            files_analyzed=10,
            total_functions=50,
            total_classes=15,
            code_targets=code_targets or [],
            complexity_hotspots=hotspots or [],
            signal_mappings={},
            token_level_targets=token_targets or [],
            summary="Test introspection report.",
        )

    def test_empty_introspection_no_proposals(self):
        """No code targets should produce no proposals."""
        report = self._make_introspection_report()
        batch = self.optimizer.generate_proposals(report)
        self.assertIsInstance(batch, ProposalBatch)
        self.assertEqual(batch.total_proposals, 0)

    def test_threshold_proposal_generation(self):
        """Threshold code targets should generate parameter_update proposals."""
        targets = [
            CodeTarget(
                file_path="maestro/aggregator.py",
                module_name="maestro.aggregator",
                target_type="parameter",
                target_name="QUORUM_THRESHOLD",
                line_number=3,
                current_value="0.66",
                optimization_category="threshold",
                rationale="Test rationale",
                linked_signals=["suspicious_consensus"],
            ),
        ]
        report = self._make_introspection_report(code_targets=targets)
        batch = self.optimizer.generate_proposals(report)
        self.assertGreater(batch.total_proposals, 0)

        proposal = batch.proposals[0]
        self.assertEqual(proposal.change_type, "parameter_update")
        self.assertEqual(proposal.category, "threshold")
        # Should propose raising for suspicious_consensus
        self.assertGreater(float(proposal.proposed_value), 0.66)

    def test_threshold_proposal_respects_bounds(self):
        """Proposals should not exceed min/max bounds."""
        targets = [
            CodeTarget(
                file_path="maestro/aggregator.py",
                module_name="maestro.aggregator",
                target_type="parameter",
                target_name="QUORUM_THRESHOLD",
                line_number=3,
                current_value="0.9",  # already at max
                optimization_category="threshold",
                rationale="Test",
                linked_signals=["suspicious_consensus"],
            ),
        ]
        report = self._make_introspection_report(code_targets=targets)
        batch = self.optimizer.generate_proposals(report)
        # Should not propose a change since already at max
        threshold_proposals = [
            p for p in batch.proposals
            if p.target_name == "QUORUM_THRESHOLD"
        ]
        self.assertEqual(len(threshold_proposals), 0)

    def test_agent_config_proposal(self):
        """Agent config targets should generate config_change proposals."""
        targets = [
            CodeTarget(
                file_path="maestro/agents/sol.py",
                module_name="maestro.agents",
                target_type="parameter",
                target_name="temperature",
                line_number=12,
                current_value="0.7",
                optimization_category="agent_config",
                rationale="Test",
                linked_signals=["suspicious_consensus"],
                metadata={"affected_agents": ["Sol"]},
            ),
        ]
        report = self._make_introspection_report(code_targets=targets)
        batch = self.optimizer.generate_proposals(report)
        self.assertGreater(batch.total_proposals, 0)
        config_proposals = [p for p in batch.proposals if p.category == "agent_config"]
        self.assertGreater(len(config_proposals), 0)

    def test_architecture_proposal_from_hotspot(self):
        """High-complexity hotspots + MAGI warnings should generate architecture proposals."""
        hotspots = [
            {
                "file": "maestro/orchestrator.py",
                "function": "run_orchestration_async",
                "line": 11,
                "complexity": 0.7,
            },
        ]
        # Architecture proposals require actionable MAGI recommendations
        magi_recs = [
            Recommendation(
                category="system",
                severity="warning",
                title="Confidence declining",
                description="System quality is declining.",
            ),
        ]
        report = self._make_introspection_report(hotspots=hotspots)
        batch = self.optimizer.generate_proposals(
            report, magi_recommendations=magi_recs,
        )
        arch_proposals = [p for p in batch.proposals if p.category == "architecture"]
        self.assertGreater(len(arch_proposals), 0)

    def test_proposal_deduplication(self):
        """Duplicate targets should not produce duplicate proposals."""
        target = CodeTarget(
            file_path="maestro/aggregator.py",
            module_name="maestro.aggregator",
            target_type="parameter",
            target_name="SIMILARITY_THRESHOLD",
            line_number=4,
            current_value="0.5",
            optimization_category="threshold",
            rationale="Test",
            linked_signals=["persistent_outlier"],
        )
        report = self._make_introspection_report(code_targets=[target, target])
        batch = self.optimizer.generate_proposals(report)
        # Should be deduplicated
        sim_proposals = [
            p for p in batch.proposals
            if p.target_name == "SIMILARITY_THRESHOLD"
        ]
        self.assertLessEqual(len(sim_proposals), 1)

    def test_proposal_has_required_fields(self):
        """Every proposal should have all required fields."""
        targets = [
            CodeTarget(
                file_path="maestro/aggregator.py",
                module_name="maestro.aggregator",
                target_type="parameter",
                target_name="QUORUM_THRESHOLD",
                line_number=3,
                current_value="0.66",
                optimization_category="threshold",
                rationale="Test",
                linked_signals=["suspicious_consensus"],
            ),
        ]
        report = self._make_introspection_report(code_targets=targets)
        batch = self.optimizer.generate_proposals(report)

        for p in batch.proposals:
            self.assertIsInstance(p, OptimizationProposal)
            self.assertTrue(len(p.proposal_id) > 0)
            self.assertTrue(len(p.timestamp) > 0)
            self.assertTrue(len(p.category) > 0)
            self.assertTrue(len(p.title) > 0)
            self.assertEqual(p.status, "proposed")

    def test_priority_breakdown(self):
        """Batch should include correct priority breakdown."""
        targets = [
            CodeTarget(
                file_path="maestro/aggregator.py",
                module_name="maestro.aggregator",
                target_type="parameter",
                target_name="QUORUM_THRESHOLD",
                line_number=3,
                current_value="0.66",
                optimization_category="threshold",
                rationale="Test",
                linked_signals=["suspicious_consensus"],
            ),
        ]
        report = self._make_introspection_report(code_targets=targets)
        batch = self.optimizer.generate_proposals(report)
        self.assertIsInstance(batch.priority_breakdown, dict)
        total_from_breakdown = sum(batch.priority_breakdown.values())
        self.assertEqual(total_from_breakdown, batch.total_proposals)


# ===========================================================================
# MAGI_VIR Tests
# ===========================================================================

class TestMagiVIR(unittest.TestCase):
    """Verify MAGI_VIR sandbox validation pipeline."""

    def setUp(self):
        self._tmpdir_session = tempfile.mkdtemp()
        self._tmpdir_r2 = tempfile.mkdtemp()
        # Patch storage dirs for isolation
        import maestro.session as session_mod
        import maestro.r2 as r2_mod
        self._original_session_dir = session_mod._DEFAULT_DIR
        self._original_r2_dir = r2_mod._DEFAULT_LEDGER_DIR
        session_mod._DEFAULT_DIR = Path(self._tmpdir_session)
        r2_mod._DEFAULT_LEDGER_DIR = Path(self._tmpdir_r2)

    def tearDown(self):
        import maestro.session as session_mod
        import maestro.r2 as r2_mod
        session_mod._DEFAULT_DIR = self._original_session_dir
        r2_mod._DEFAULT_LEDGER_DIR = self._original_r2_dir
        shutil.rmtree(self._tmpdir_session, ignore_errors=True)
        shutil.rmtree(self._tmpdir_r2, ignore_errors=True)

    def _make_proposal(self, target_name="QUORUM_THRESHOLD",
                        current_value="0.66", proposed_value="0.71"):
        return OptimizationProposal(
            proposal_id="test-proposal-1",
            timestamp="2024-01-01T00:00:00Z",
            category="threshold",
            priority="high",
            title="Test proposal",
            description="Test description",
            file_path="maestro/aggregator.py",
            module_name="maestro.aggregator",
            target_name=target_name,
            line_number=3,
            current_value=current_value,
            proposed_value=proposed_value,
            change_type="parameter_update",
        )

    def test_vir_has_unique_id(self):
        """Each VIR instance should have a unique ID."""
        vir1 = MagiVIR()
        vir2 = MagiVIR()
        self.assertNotEqual(vir1.vir_id, vir2.vir_id)

    def test_vir_validate_with_proposals(self):
        """VIR should validate proposals and produce a report."""
        vir = MagiVIR(benchmark_prompts=["Test prompt 1", "Test prompt 2"])
        proposal = self._make_proposal()
        report = vir.validate([proposal])

        self.assertIsInstance(report, VIRReport)
        self.assertEqual(report.benchmark_count, 2)
        self.assertEqual(len(report.comparisons), 2)
        self.assertIn(report.recommendation, ("promote", "reject", "needs_review"))
        self.assertTrue(len(report.summary) > 0)
        self.assertEqual(report.isolation_tier, "local_sandbox")

    def test_vir_comparison_fields(self):
        """Each comparison should have all required fields."""
        vir = MagiVIR(benchmark_prompts=["Test prompt"])
        proposal = self._make_proposal()
        report = vir.validate([proposal])

        for comp in report.comparisons:
            self.assertIsInstance(comp, VIRComparison)
            self.assertIsInstance(comp.baseline, BenchmarkResult)
            self.assertIsInstance(comp.optimized, BenchmarkResult)
            self.assertIsInstance(comp.confidence_delta, float)
            self.assertIsInstance(comp.drift_delta, float)
            self.assertIsInstance(comp.grade_improved, bool)
            self.assertIsInstance(comp.collapse_fixed, bool)

    def test_vir_sandbox_cleanup(self):
        """Sandbox should be cleaned up after validation."""
        vir = MagiVIR(benchmark_prompts=["Test"])
        proposal = self._make_proposal()
        vir.validate([proposal])
        # After validation, work_dir should be None (cleaned up)
        self.assertIsNone(vir._work_dir)

    def test_vir_grade_ranking(self):
        """Grade ranking should order correctly."""
        self.assertGreater(MagiVIR._grade_rank("strong"), MagiVIR._grade_rank("weak"))
        self.assertGreater(MagiVIR._grade_rank("acceptable"), MagiVIR._grade_rank("suspicious"))
        self.assertEqual(MagiVIR._grade_rank("unknown"), -1)

    def test_vir_overall_improvement_range(self):
        """Overall improvement should be in -1 to 1 range."""
        vir = MagiVIR(benchmark_prompts=["Test prompt"])
        proposal = self._make_proposal()
        report = vir.validate([proposal])
        self.assertGreaterEqual(report.overall_improvement, -1.0)
        self.assertLessEqual(report.overall_improvement, 1.0)

    def test_vir_node_id(self):
        """VIR should report its compute node."""
        vir = MagiVIR(compute_node="test-node-1")
        self.assertEqual(vir.node_id, "test-node-1")

    def test_vir_validate_batch(self):
        """validate_batch should work with a ProposalBatch."""
        batch = ProposalBatch(
            batch_id="test-batch",
            timestamp="2024-01-01T00:00:00Z",
            proposals=[self._make_proposal()],
            source_report="test",
            summary="Test batch",
            total_proposals=1,
            priority_breakdown={"high": 1},
        )
        vir = MagiVIR(benchmark_prompts=["Test"])
        report = vir.validate_batch(batch)
        self.assertIsInstance(report, VIRReport)


# ===========================================================================
# Compute Node Registry Tests
# ===========================================================================

class TestComputeNodeRegistry(unittest.TestCase):
    """Verify compute node registration and selection."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.registry = ComputeNodeRegistry(registry_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_register_and_get(self):
        node = ComputeNode(
            node_id="node-1",
            host="192.168.1.100",
            port=8000,
            status="available",
            capabilities=["local_sandbox"],
        )
        self.registry.register(node)
        loaded = self.registry.get("node-1")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.host, "192.168.1.100")
        self.assertEqual(loaded.status, "available")

    def test_list_available(self):
        self.registry.register(ComputeNode(
            node_id="node-1", host="host1", status="available",
        ))
        self.registry.register(ComputeNode(
            node_id="node-2", host="host2", status="offline",
        ))
        self.registry.register(ComputeNode(
            node_id="node-3", host="host3", status="available",
        ))
        available = self.registry.list_available()
        self.assertEqual(len(available), 2)

    def test_select_node_with_capabilities(self):
        self.registry.register(ComputeNode(
            node_id="node-1", host="host1", status="available",
            capabilities=["local_sandbox"],
        ))
        self.registry.register(ComputeNode(
            node_id="node-2", host="host2", status="available",
            capabilities=["local_sandbox", "full_pipeline"],
        ))
        node = self.registry.select_node(required_capabilities=["full_pipeline"])
        self.assertIsNotNone(node)
        self.assertEqual(node.node_id, "node-2")

    def test_select_node_none_available(self):
        node = self.registry.select_node()
        self.assertIsNone(node)

    def test_unregister(self):
        self.registry.register(ComputeNode(node_id="node-1", host="host1"))
        self.assertTrue(self.registry.unregister("node-1"))
        self.assertIsNone(self.registry.get("node-1"))

    def test_unregister_nonexistent(self):
        self.assertFalse(self.registry.unregister("nonexistent"))

    def test_update_status(self):
        self.registry.register(ComputeNode(
            node_id="node-1", host="host1", status="available",
        ))
        self.assertTrue(self.registry.update_status("node-1", "busy"))
        node = self.registry.get("node-1")
        self.assertEqual(node.status, "busy")


# ===========================================================================
# Self-Improvement Engine Tests
# ===========================================================================

class TestSelfImprovementEngine(unittest.TestCase):
    """Verify the full self-improvement orchestration loop."""

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

    def tearDown(self):
        import maestro.session as session_mod
        import maestro.r2 as r2_mod
        session_mod._DEFAULT_DIR = self._original_session_dir
        r2_mod._DEFAULT_LEDGER_DIR = self._original_r2_dir
        for d in (self._r2_dir, self._session_dir, self._improve_dir,
                  self._tmpdir_session, self._tmpdir_r2):
            shutil.rmtree(d, ignore_errors=True)

    def _populate_ledger(self, count=5, collapse=False, outlier_agents=None):
        """Add entries to the R2 ledger."""
        for i in range(count):
            dissent = DissentReport(
                prompt=f"prompt {i}",
                internal_agreement=0.95 if collapse else 0.8,
                pairwise=[],
                agent_profiles=[],
                outlier_agents=outlier_agents or [],
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

    def test_empty_ledger_no_proposals(self):
        """Engine should handle empty ledger gracefully."""
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test"],
        )
        cycle = engine.run_cycle()
        self.assertIsInstance(cycle, ImprovementCycle)
        self.assertEqual(cycle.phase, "complete")
        self.assertEqual(cycle.outcome, "no_proposals")
        self.assertEqual(cycle.proposal_count, 0)

    def test_cycle_with_signals(self):
        """Cycle with ledger data should produce proposals and validate."""
        self._populate_ledger(count=5, collapse=True)
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test prompt"],
        )
        cycle = engine.run_cycle()
        self.assertIsInstance(cycle, ImprovementCycle)
        self.assertEqual(cycle.phase, "complete")
        self.assertIn(cycle.outcome, ("promoted", "rejected", "needs_review"))
        self.assertIsNotNone(cycle.magi_report)
        self.assertIsNotNone(cycle.introspection_summary)

    def test_cycle_persisted(self):
        """Cycle should be persisted to disk."""
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test"],
        )
        cycle = engine.run_cycle()
        loaded = engine.load_cycle(cycle.cycle_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["cycle_id"], cycle.cycle_id)

    def test_list_cycles(self):
        """Should list recorded cycles."""
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test"],
        )
        engine.run_cycle()
        engine.run_cycle()

        cycles = engine.list_cycles()
        self.assertEqual(len(cycles), 2)
        for c in cycles:
            self.assertIn("cycle_id", c)
            self.assertIn("outcome", c)
            self.assertIn("timestamp", c)

    def test_count_cycles(self):
        """Should count total cycles."""
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test"],
        )
        self.assertEqual(engine.count_cycles(), 0)
        engine.run_cycle()
        self.assertEqual(engine.count_cycles(), 1)

    def test_analysis_only_mode(self):
        """run_analysis_only should not validate in VIR."""
        self._populate_ledger(count=5, collapse=True)
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
        )
        result = engine.run_analysis_only()
        self.assertIn("magi_report", result)
        self.assertIn("introspection_summary", result)
        self.assertIn("proposals", result)
        self.assertIn("proposal_count", result)

    def test_cycle_duration_tracked(self):
        """Cycle should track duration in milliseconds."""
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test"],
        )
        cycle = engine.run_cycle()
        self.assertGreater(cycle.duration_ms, 0)

    def test_cycle_fields(self):
        """Cycle should have all required fields."""
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=self.session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test"],
        )
        cycle = engine.run_cycle()
        self.assertTrue(len(cycle.cycle_id) > 0)
        self.assertTrue(len(cycle.timestamp) > 0)
        self.assertIn(cycle.phase, ("analysis", "introspection", "proposal",
                                     "validation", "complete", "failed"))
        self.assertIn(cycle.outcome, ("pending", "promoted", "rejected",
                                       "needs_review", "no_proposals"))


# ===========================================================================
# MAGI Code Optimization Analysis Tests
# ===========================================================================

class TestMagiCodeOptimization(unittest.TestCase):
    """Verify MAGI's code-optimization-aware analysis."""

    def setUp(self):
        self._r2_dir = tempfile.mkdtemp()
        self._session_dir = tempfile.mkdtemp()
        self.r2 = R2Engine(ledger_dir=self._r2_dir)

        from maestro.session import SessionLogger
        self.session_logger = SessionLogger(storage_dir=self._session_dir)

    def tearDown(self):
        shutil.rmtree(self._r2_dir, ignore_errors=True)
        shutil.rmtree(self._session_dir, ignore_errors=True)

    def _populate_ledger(self, count=5, collapse=False):
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

    def test_analyze_with_introspection_empty(self):
        """Should handle empty ledger gracefully."""
        magi = Magi(r2=self.r2, session_logger=self.session_logger)
        result = magi.analyze_with_introspection()
        self.assertIn("report", result)
        self.assertIn("code_targets", result)
        self.assertIn("optimization_proposals", result)
        self.assertIn("introspection_summary", result)

    def test_analyze_with_introspection_populated(self):
        """Should produce code targets when ledger has data."""
        self._populate_ledger(count=5, collapse=True)
        magi = Magi(r2=self.r2, session_logger=self.session_logger)
        result = magi.analyze_with_introspection()

        report = result["report"]
        self.assertIsInstance(report, MagiReport)
        self.assertGreater(report.ledger_entries_analyzed, 0)

        # Should have code targets from signal mapping
        self.assertIsInstance(result["code_targets"], list)
        self.assertIsInstance(result["optimization_proposals"], list)

    def test_code_optimization_recommendations(self):
        """MAGI should produce code_optimization category recommendations."""
        self._populate_ledger(count=5, collapse=True)
        magi = Magi(r2=self.r2, session_logger=self.session_logger)
        result = magi.analyze_with_introspection()

        report = result["report"]
        code_recs = [
            r for r in report.recommendations
            if r.category == "code_optimization"
        ]
        # When there are proposals, there should be code_optimization recs
        if result["optimization_proposals"]:
            self.assertGreater(len(code_recs), 0)

    def test_introspection_summary_not_empty(self):
        """Introspection summary should always be populated."""
        magi = Magi(r2=self.r2, session_logger=self.session_logger)
        result = magi.analyze_with_introspection()
        self.assertIsInstance(result["introspection_summary"], str)
        self.assertGreater(len(result["introspection_summary"]), 0)

    def test_proposal_batch_returned(self):
        """Should return the ProposalBatch object for downstream use."""
        self._populate_ledger(count=3, collapse=True)
        magi = Magi(r2=self.r2, session_logger=self.session_logger)
        result = magi.analyze_with_introspection()
        self.assertIn("proposal_batch", result)
        self.assertIsInstance(result["proposal_batch"], ProposalBatch)


# ===========================================================================
# Integration: Full Pipeline Test
# ===========================================================================

class TestSelfImprovementIntegration(unittest.TestCase):
    """End-to-end test of the self-improvement pipeline."""

    def setUp(self):
        self._r2_dir = tempfile.mkdtemp()
        self._session_dir = tempfile.mkdtemp()
        self._improve_dir = tempfile.mkdtemp()
        self._tmpdir_session = tempfile.mkdtemp()
        self._tmpdir_r2 = tempfile.mkdtemp()

        self.r2 = R2Engine(ledger_dir=self._r2_dir)

        import maestro.session as session_mod
        import maestro.r2 as r2_mod
        self._original_session_dir = session_mod._DEFAULT_DIR
        self._original_r2_dir = r2_mod._DEFAULT_LEDGER_DIR
        session_mod._DEFAULT_DIR = Path(self._tmpdir_session)
        r2_mod._DEFAULT_LEDGER_DIR = Path(self._tmpdir_r2)

    def tearDown(self):
        import maestro.session as session_mod
        import maestro.r2 as r2_mod
        session_mod._DEFAULT_DIR = self._original_session_dir
        r2_mod._DEFAULT_LEDGER_DIR = self._original_r2_dir
        for d in (self._r2_dir, self._session_dir, self._improve_dir,
                  self._tmpdir_session, self._tmpdir_r2):
            shutil.rmtree(d, ignore_errors=True)

    def test_full_pipeline_collapse_scenario(self):
        """
        Full pipeline test: simulate a system with frequent silent collapses,
        run the self-improvement loop, and verify it produces proposals to fix it.
        """
        # Simulate 5 sessions with silent collapse
        for i in range(5):
            dissent = DissentReport(
                prompt=f"ethics question {i}",
                internal_agreement=0.95,
                pairwise=[],
                agent_profiles=[],
                outlier_agents=[],
                dissent_level="none",
                agent_count=3,
            )
            drift = DriftReport(
                prompt=f"ethics question {i}",
                ncg_content="raw unframed baseline output",
                ncg_model="mock-headless-v1",
                agent_signals=[],
                mean_semantic_distance=0.65,
                max_semantic_distance=0.72,
                silent_collapse_detected=True,
                compression_alert=False,
            )
            score = self.r2.score_session(dissent, drift, quorum_confidence="High")
            signals = self.r2.detect_signals(score, dissent, drift)
            self.r2.index(
                session_id=f"collapse-sess-{i}",
                prompt=f"ethics question {i}",
                consensus="generic safe answer",
                agents_agreed=["Sol", "Aria", "Prism"],
                score=score,
                improvement_signals=signals,
                dissent_report=dissent,
                drift_report=drift,
            )

        # Run the self-improvement loop
        session_logger = SessionLogger(storage_dir=self._session_dir)
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test prompt for validation"],
        )
        cycle = engine.run_cycle()

        # Verify: the system identified the collapse pattern
        self.assertEqual(cycle.phase, "complete")
        self.assertIsNotNone(cycle.magi_report)

        # Should have detected the collapse pattern in MAGI
        magi_recs = cycle.magi_report.get("recommendations", [])
        critical_recs = [r for r in magi_recs if r.get("severity") == "critical"]
        self.assertGreater(len(critical_recs), 0)

        # Should have generated proposals
        self.assertGreater(cycle.proposal_count, 0)

        # Should have VIR validation results
        self.assertIsNotNone(cycle.vir_report)
        self.assertIn(cycle.outcome, ("promoted", "rejected", "needs_review"))

    def test_full_pipeline_healthy_system(self):
        """
        A healthy system should produce no proposals (or only positive ones).
        """
        for i in range(5):
            dissent = DissentReport(
                prompt=f"question {i}",
                internal_agreement=0.8,
                pairwise=[],
                agent_profiles=[],
                outlier_agents=[],
                dissent_level="low",
                agent_count=3,
            )
            drift = DriftReport(
                prompt=f"question {i}",
                ncg_content="baseline",
                ncg_model="mock",
                agent_signals=[],
                mean_semantic_distance=0.2,
                max_semantic_distance=0.3,
                silent_collapse_detected=False,
                compression_alert=False,
            )
            score = self.r2.score_session(dissent, drift, quorum_confidence="High")
            signals = self.r2.detect_signals(score, dissent, drift)
            self.r2.index(
                session_id=f"healthy-sess-{i}",
                prompt=f"question {i}",
                consensus="thoughtful answer",
                agents_agreed=["Sol", "Aria", "Prism"],
                score=score,
                improvement_signals=signals,
                dissent_report=dissent,
                drift_report=drift,
            )

        session_logger = SessionLogger(storage_dir=self._session_dir)
        engine = SelfImprovementEngine(
            r2=self.r2,
            session_logger=session_logger,
            improvement_dir=self._improve_dir,
            benchmark_prompts=["Test"],
        )
        cycle = engine.run_cycle()

        self.assertEqual(cycle.phase, "complete")
        # Healthy system should generate few or no proposals
        # (no signals to map to code targets)
        self.assertEqual(cycle.outcome, "no_proposals")


if __name__ == "__main__":
    unittest.main()
