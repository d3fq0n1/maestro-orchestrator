import asyncio
import os
import shutil
import tempfile
import unittest
from maestro.orchestrator import run_orchestration, run_orchestration_async
from maestro.agents import Agent, MockAgent, Sol, Aria, Prism, TempAgent
from maestro.aggregator import analyze_agreement, aggregate_responses, QUORUM_THRESHOLD
from maestro.ncg.generator import MockHeadlessGenerator
from maestro.ncg.drift import DriftDetector, DriftReport
from maestro.dissent import DissentAnalyzer, DissentReport, PairwiseDissent, AgentDissentProfile
from maestro.session import SessionLogger, SessionRecord, build_session_record
from maestro.r2 import R2Engine, R2Score, ImprovementSignal, R2LedgerEntry


class TestAgentInterface(unittest.TestCase):
    """Verify all agent classes follow the base interface."""

    def test_mock_agent_is_agent(self):
        agent = MockAgent(name="Test")
        self.assertIsInstance(agent, Agent)

    def test_sol_is_agent(self):
        self.assertIsInstance(Sol(), Agent)

    def test_aria_is_agent(self):
        self.assertIsInstance(Aria(), Agent)

    def test_prism_is_agent(self):
        self.assertIsInstance(Prism(), Agent)

    def test_tempagent_is_agent(self):
        self.assertIsInstance(TempAgent(), Agent)

    def test_mock_agent_fetch(self):
        agent = MockAgent(name="TestBot", response_style="empathic")
        result = asyncio.run(agent.fetch("test"))
        self.assertIn("TestBot", result)
        self.assertIn("empathy", result)

    def test_mock_agent_styles(self):
        for style in ("neutral", "empathic", "historical"):
            agent = MockAgent(name="A", response_style=style)
            result = asyncio.run(agent.fetch("q"))
            self.assertIn("[A]", result)

    def test_agent_name_and_model(self):
        sol = Sol()
        self.assertEqual(sol.name, "Sol")
        self.assertEqual(sol.model, "gpt-4")

        aria = Aria()
        self.assertEqual(aria.name, "Aria")
        self.assertEqual(aria.model, "claude-3-opus-20240229")

        prism = Prism()
        self.assertEqual(prism.name, "Prism")

        temp = TempAgent()
        self.assertEqual(temp.name, "TempAgent")

    def test_agent_custom_model(self):
        sol = Sol(model="gpt-4-turbo")
        self.assertEqual(sol.model, "gpt-4-turbo")

        aria = Aria(model="claude-3-sonnet-20240229")
        self.assertEqual(aria.model, "claude-3-sonnet-20240229")

    def test_agents_without_keys_return_error(self):
        """Agents should return an error string when API keys are missing."""
        saved = {}
        for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"):
            saved[key] = os.environ.pop(key, None)

        try:
            for agent_cls in (Sol, Aria, Prism, TempAgent):
                agent = agent_cls()
                result = asyncio.run(agent.fetch("test"))
                self.assertIn("API Key Missing", result)
        finally:
            for key, val in saved.items():
                if val is not None:
                    os.environ[key] = val


class TestMaestroOrchestration(unittest.TestCase):

    def test_mock_responses(self):
        prompt = "What is the meaning of life?"
        result = run_orchestration(prompt, session_logging=False)

        self.assertIn("responses", result)
        self.assertEqual(len(result["responses"]), 2)

        self.assertIn("final_output", result)
        final = result["final_output"]

        self.assertIn("consensus", final)
        self.assertIn("majority_view", final)
        self.assertIn("confidence", final)
        self.assertIn("note", final)

        self.assertIsInstance(final["consensus"], str)
        self.assertIsInstance(final["majority_view"], str)
        self.assertIsInstance(final["confidence"], str)

    def test_orchestration_with_ncg(self):
        prompt = "What is the meaning of life?"
        result = run_orchestration(prompt, ncg_enabled=True, session_logging=False)

        final = result["final_output"]
        self.assertIn("ncg_benchmark", final)

        benchmark = final["ncg_benchmark"]
        self.assertIn("ncg_model", benchmark)
        self.assertIn("mean_drift", benchmark)
        self.assertIn("max_drift", benchmark)
        self.assertIn("silent_collapse", benchmark)
        self.assertIn("compression_alert", benchmark)
        self.assertIn("per_agent", benchmark)
        self.assertEqual(len(benchmark["per_agent"]), 2)

    def test_orchestration_ncg_disabled(self):
        prompt = "What is the meaning of life?"
        result = run_orchestration(prompt, ncg_enabled=False, session_logging=False)

        final = result["final_output"]
        self.assertNotIn("ncg_benchmark", final)

    def test_named_responses_in_output(self):
        """The orchestrator should return agent-keyed responses."""
        result = run_orchestration("test", session_logging=False)
        self.assertIn("named_responses", result)
        self.assertIsInstance(result["named_responses"], dict)
        self.assertEqual(len(result["named_responses"]), 2)
        for name in result["named_responses"]:
            self.assertIsInstance(name, str)

    def test_custom_headless_generator(self):
        """A custom headless generator should be used when provided."""
        result = asyncio.run(run_orchestration_async(
            "test",
            ncg_enabled=True,
            session_logging=False,
            headless_generator=MockHeadlessGenerator(),
        ))
        final = result["final_output"]
        self.assertIn("ncg_benchmark", final)
        self.assertEqual(final["ncg_benchmark"]["ncg_model"], "mock-headless-v1")


class TestSemanticQuorum(unittest.TestCase):
    """Verify semantic similarity-based quorum logic."""

    def _make_dissent_report(self, agent_responses, prompt="test"):
        """Helper: run dissent analysis to get a real report with pairwise distances."""
        analyzer = DissentAnalyzer()
        return analyzer.analyze(prompt, agent_responses)

    def test_identical_responses_high_quorum(self):
        """Identical responses should produce agreement_ratio of 1.0."""
        responses = {
            "Sol": "the answer is 42",
            "Aria": "the answer is 42",
            "Prism": "the answer is 42",
        }
        report = self._make_dissent_report(responses)
        confidence, ratio, majority, dissenting = analyze_agreement(responses, report)
        self.assertEqual(ratio, 1.0)
        self.assertEqual(confidence, "High")
        self.assertEqual(len(dissenting), 0)

    def test_similar_responses_reach_quorum(self):
        """Similar but not identical responses should still cluster together."""
        responses = {
            "Sol": "cats are wonderful pets for families with children",
            "Aria": "cats make wonderful pets for families",
            "Prism": "quantum mechanics describes subatomic particle behavior",
        }
        report = self._make_dissent_report(responses)
        confidence, ratio, majority, dissenting = analyze_agreement(responses, report)
        # Sol and Aria should cluster (similar), Prism is the outlier
        # 2/3 = 0.66... which meets the 66% threshold
        self.assertGreaterEqual(ratio, QUORUM_THRESHOLD)
        self.assertEqual(len(dissenting), 1)

    def test_all_different_low_quorum(self):
        """Completely unrelated responses should produce low agreement."""
        responses = {
            "Sol": "cats are wonderful household companions",
            "Aria": "quantum mechanics describes particle behavior",
            "Prism": "the french revolution began in 1789",
        }
        report = self._make_dissent_report(responses)
        confidence, ratio, majority, dissenting = analyze_agreement(responses, report)
        # Each agent is on a different topic, no cluster > 1
        self.assertLessEqual(ratio, 0.5)

    def test_quorum_fields_in_orchestration_output(self):
        """Orchestration output should contain quorum metadata."""
        result = run_orchestration("test", session_logging=False)
        final = result["final_output"]
        self.assertIn("agreement_ratio", final)
        self.assertIn("quorum_met", final)
        self.assertIn("quorum_threshold", final)
        self.assertIsInstance(final["agreement_ratio"], float)
        self.assertIsInstance(final["quorum_met"], bool)
        self.assertEqual(final["quorum_threshold"], QUORUM_THRESHOLD)

    def test_fallback_without_dissent_report(self):
        """Without a dissent report, falls back to exact string matching."""
        responses = ["answer A", "answer A", "answer B"]
        confidence, ratio, majority, dissenting = analyze_agreement(responses)
        self.assertAlmostEqual(ratio, 2 / 3, places=2)
        self.assertEqual(majority, "answer A")
        self.assertEqual(len(dissenting), 1)

    def test_agreement_ratio_range(self):
        """Agreement ratio should always be between 0 and 1."""
        responses = {
            "Sol": "hello",
            "Aria": "world",
        }
        report = self._make_dissent_report(responses)
        _, ratio, _, _ = analyze_agreement(responses, report)
        self.assertGreaterEqual(ratio, 0.0)
        self.assertLessEqual(ratio, 1.0)


class TestNCGGenerator(unittest.TestCase):

    def test_mock_headless_generate(self):
        gen = MockHeadlessGenerator()
        output = gen.generate("test prompt")

        self.assertIn("content", output)
        self.assertIn("model", output)
        self.assertIn("metadata", output)
        self.assertEqual(output["model"], "mock-headless-v1")
        self.assertFalse(output["metadata"]["logprobs_available"])
        self.assertEqual(output["metadata"]["framing"], "none")

    def test_mock_headless_model_id(self):
        gen = MockHeadlessGenerator()
        self.assertEqual(gen.model_id, "mock-headless-v1")


class TestDriftDetector(unittest.TestCase):

    def test_basic_drift_analysis(self):
        gen = MockHeadlessGenerator()
        ncg_output = gen.generate("test prompt")

        conversational = {
            "Agent1": "This is a helpful and polite response about test prompt.",
            "Agent2": "Here is my balanced and considerate take on test prompt.",
        }

        detector = DriftDetector()
        report = detector.analyze(
            prompt="test prompt",
            ncg_output=ncg_output,
            conversational_outputs=conversational,
        )

        self.assertIsInstance(report, DriftReport)
        self.assertEqual(len(report.agent_signals), 2)
        self.assertGreaterEqual(report.mean_semantic_distance, 0.0)
        self.assertLessEqual(report.mean_semantic_distance, 1.0)

    def test_silent_collapse_detection(self):
        gen = MockHeadlessGenerator()
        ncg_output = gen.generate("complex ethical question")

        conversational = {
            "Agent1": "completely unrelated topic about weather patterns",
            "Agent2": "also about weather patterns and not the actual question",
        }

        detector = DriftDetector()
        report = detector.analyze(
            prompt="complex ethical question",
            ncg_output=ncg_output,
            conversational_outputs=conversational,
            internal_agreement=0.95,
        )

        self.assertTrue(report.mean_semantic_distance > 0.0)

    def test_compression_ratio(self):
        detector = DriftDetector()
        ratio = detector._compression_ratio("short", "this is a much longer baseline text")
        self.assertLess(ratio, 1.0)

    def test_semantic_distance_identical(self):
        detector = DriftDetector()
        distance = detector._semantic_distance("hello world", "hello world")
        self.assertEqual(distance, 0.0)


class TestDissentAnalyzer(unittest.TestCase):
    """Verify internal dissent measurement across agent responses."""

    def test_identical_responses_no_dissent(self):
        analyzer = DissentAnalyzer()
        report = analyzer.analyze("test", {
            "Sol": "the answer is 42",
            "Aria": "the answer is 42",
        })
        self.assertIsInstance(report, DissentReport)
        self.assertEqual(report.internal_agreement, 1.0)
        self.assertEqual(report.dissent_level, "none")
        self.assertEqual(len(report.pairwise), 1)

    def test_different_responses_show_dissent(self):
        analyzer = DissentAnalyzer()
        report = analyzer.analyze("test", {
            "Sol": "the answer is clearly about philosophy and meaning",
            "Aria": "weather patterns indicate rain tomorrow in the northeast",
        })
        self.assertLess(report.internal_agreement, 1.0)
        self.assertGreater(report.pairwise[0].distance, 0.0)

    def test_three_agents_pairwise_count(self):
        analyzer = DissentAnalyzer()
        report = analyzer.analyze("test", {
            "Sol": "response one",
            "Aria": "response two",
            "Prism": "response three",
        })
        # 3 agents = 3 pairs: (Sol,Aria), (Sol,Prism), (Aria,Prism)
        self.assertEqual(len(report.pairwise), 3)
        self.assertEqual(len(report.agent_profiles), 3)
        self.assertEqual(report.agent_count, 3)

    def test_outlier_detection(self):
        analyzer = DissentAnalyzer()
        report = analyzer.analyze("test", {
            "Sol": "cats are great pets for families",
            "Aria": "cats make wonderful household companions",
            "Prism": "quantum mechanics governs subatomic particle behavior",
        })
        # Prism is talking about something completely different
        # It should have a higher mean distance to others
        prism_profile = [p for p in report.agent_profiles if p.agent_name == "Prism"][0]
        sol_profile = [p for p in report.agent_profiles if p.agent_name == "Sol"][0]
        self.assertGreater(prism_profile.mean_distance_to_others,
                           sol_profile.mean_distance_to_others)

    def test_agreement_score_range(self):
        analyzer = DissentAnalyzer()
        report = analyzer.analyze("test", {
            "Sol": "hello world",
            "Aria": "goodbye world",
        })
        self.assertGreaterEqual(report.internal_agreement, 0.0)
        self.assertLessEqual(report.internal_agreement, 1.0)

    def test_dissent_level_classification(self):
        analyzer = DissentAnalyzer()
        # Identical => none
        report = analyzer.analyze("test", {
            "A": "same text here",
            "B": "same text here",
        })
        self.assertEqual(report.dissent_level, "none")

    def test_two_agents_no_outlier(self):
        """Outlier detection requires at least 3 agents."""
        analyzer = DissentAnalyzer()
        report = analyzer.analyze("test", {
            "Sol": "apples",
            "Aria": "quantum physics",
        })
        self.assertEqual(report.outlier_agents, [])

    def test_cross_session_analysis(self):
        analyzer = DissentAnalyzer()
        sessions = [
            {"prompt": "q1", "agent_responses": {"Sol": "a", "Aria": "b"}},
            {"prompt": "q2", "agent_responses": {"Sol": "c", "Aria": "d"}},
            {"prompt": "q3", "agent_responses": {"Sol": "e", "Aria": "f"}},
            {"prompt": "q4", "agent_responses": {"Sol": "g", "Aria": "h"}},
        ]
        result = analyzer.analyze_across_sessions(sessions)
        self.assertEqual(result["sessions_analyzed"], 4)
        self.assertIn("Sol", result["per_agent"])
        self.assertIn("Aria", result["per_agent"])
        self.assertIn(result["trend"], ("stable", "converging", "diverging"))

    def test_cross_session_skips_single_agent(self):
        analyzer = DissentAnalyzer()
        sessions = [
            {"prompt": "q1", "agent_responses": {"Sol": "only one"}},
        ]
        result = analyzer.analyze_across_sessions(sessions)
        self.assertEqual(result["sessions_analyzed"], 0)


class TestOrchestrationDissentIntegration(unittest.TestCase):
    """Verify dissent analysis flows through the orchestrator output."""

    def test_dissent_in_final_output(self):
        result = run_orchestration("test", session_logging=False)
        final = result["final_output"]
        self.assertIn("dissent", final)

        dissent = final["dissent"]
        self.assertIn("internal_agreement", dissent)
        self.assertIn("dissent_level", dissent)
        self.assertIn("outlier_agents", dissent)
        self.assertIn("pairwise", dissent)
        self.assertIn("agent_profiles", dissent)

        self.assertGreaterEqual(dissent["internal_agreement"], 0.0)
        self.assertLessEqual(dissent["internal_agreement"], 1.0)


class TestSessionLogger(unittest.TestCase):
    """Verify session persistence: write, read, list, delete."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.logger = SessionLogger(storage_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_record(self, prompt="test prompt"):
        return build_session_record(
            prompt=prompt,
            agent_responses={"Sol": "response A", "Aria": "response B"},
            final_output={
                "consensus": "merged",
                "majority_view": "response A",
                "minority_view": None,
                "confidence": "High",
                "note": "test",
            },
            ncg_enabled=False,
        )

    def test_save_and_load(self):
        record = self._make_record()
        self.logger.save(record)

        loaded = self.logger.load(record.session_id)
        self.assertEqual(loaded.session_id, record.session_id)
        self.assertEqual(loaded.prompt, "test prompt")
        self.assertEqual(loaded.agent_responses["Sol"], "response A")
        self.assertEqual(loaded.agents_used, ["Sol", "Aria"])

    def test_list_sessions(self):
        for i in range(3):
            self.logger.save(self._make_record(f"prompt {i}"))

        summaries = self.logger.list_sessions()
        self.assertEqual(len(summaries), 3)
        for s in summaries:
            self.assertIn("session_id", s)
            self.assertIn("timestamp", s)
            self.assertIn("prompt", s)

    def test_list_sessions_limit_offset(self):
        for i in range(5):
            self.logger.save(self._make_record(f"prompt {i}"))

        page = self.logger.list_sessions(limit=2, offset=1)
        self.assertEqual(len(page), 2)

    def test_count(self):
        self.assertEqual(self.logger.count(), 0)
        self.logger.save(self._make_record())
        self.assertEqual(self.logger.count(), 1)

    def test_delete(self):
        record = self._make_record()
        self.logger.save(record)
        self.assertEqual(self.logger.count(), 1)

        deleted = self.logger.delete(record.session_id)
        self.assertTrue(deleted)
        self.assertEqual(self.logger.count(), 0)

    def test_delete_nonexistent(self):
        self.assertFalse(self.logger.delete("nonexistent-id"))

    def test_load_nonexistent_raises(self):
        with self.assertRaises(FileNotFoundError):
            self.logger.load("nonexistent-id")

    def test_session_record_has_uuid_and_timestamp(self):
        record = self._make_record()
        self.assertTrue(len(record.session_id) > 0)
        self.assertIn("T", record.timestamp)  # ISO format

    def test_ncg_benchmark_persisted(self):
        record = build_session_record(
            prompt="test",
            agent_responses={"Sol": "a"},
            final_output={
                "consensus": "m",
                "majority_view": "a",
                "minority_view": None,
                "confidence": "High",
                "note": "test",
                "ncg_benchmark": {
                    "ncg_model": "mock-headless-v1",
                    "mean_drift": 0.42,
                    "silent_collapse": False,
                },
            },
            ncg_enabled=True,
        )
        self.logger.save(record)
        loaded = self.logger.load(record.session_id)
        self.assertEqual(loaded.ncg_benchmark["mean_drift"], 0.42)

    def test_list_all_ids(self):
        records = [self._make_record(f"p{i}") for i in range(3)]
        for r in records:
            self.logger.save(r)
        ids = self.logger.list_all_ids()
        self.assertEqual(len(ids), 3)


class TestOrchestrationSessionIntegration(unittest.TestCase):
    """Verify the orchestrator writes session records when enabled."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        # Patch the default storage dir so tests don't pollute real data
        import maestro.session as session_mod
        self._original_dir = session_mod._DEFAULT_DIR
        session_mod._DEFAULT_DIR = __import__("pathlib").Path(self._tmpdir)

    def tearDown(self):
        import maestro.session as session_mod
        session_mod._DEFAULT_DIR = self._original_dir
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_orchestration_creates_session_file(self):
        result = run_orchestration("test prompt", session_logging=True)
        self.assertIn("session_id", result)
        self.assertIsNotNone(result["session_id"])

        logger = SessionLogger(storage_dir=self._tmpdir)
        self.assertEqual(logger.count(), 1)

        loaded = logger.load(result["session_id"])
        self.assertEqual(loaded.prompt, "test prompt")

    def test_orchestration_session_logging_disabled(self):
        result = run_orchestration("test prompt", session_logging=False)
        self.assertIsNone(result["session_id"])

        logger = SessionLogger(storage_dir=self._tmpdir)
        self.assertEqual(logger.count(), 0)


class TestR2Engine(unittest.TestCase):
    """Verify R2 scoring, signal detection, ledger persistence, and trends."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.r2 = R2Engine(ledger_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_dissent_report(self, agreement=0.8, dissent_level="low",
                             outlier_agents=None):
        return DissentReport(
            prompt="test prompt",
            internal_agreement=agreement,
            pairwise=[],
            agent_profiles=[],
            outlier_agents=outlier_agents or [],
            dissent_level=dissent_level,
            agent_count=3,
        )

    def _make_drift_report(self, mean_drift=0.3, collapse=False,
                           compression=False):
        return DriftReport(
            prompt="test prompt",
            ncg_content="headless baseline content for test prompt",
            ncg_model="mock-headless-v1",
            agent_signals=[],
            mean_semantic_distance=mean_drift,
            max_semantic_distance=mean_drift + 0.1,
            silent_collapse_detected=collapse,
            compression_alert=compression,
        )

    # --- Scoring tests ---

    def test_strong_grade(self):
        """Clean session with no flags should score 'strong'."""
        dissent = self._make_dissent_report(agreement=0.8, dissent_level="low")
        drift = self._make_drift_report(mean_drift=0.2)
        score = self.r2.score_session(dissent, drift, quorum_confidence="High")
        self.assertEqual(score.grade, "strong")
        self.assertEqual(score.flags, [])
        self.assertGreater(score.confidence_score, 0.5)

    def test_suspicious_grade_silent_collapse(self):
        """Silent collapse triggers 'suspicious' grade."""
        dissent = self._make_dissent_report(agreement=0.95)
        drift = self._make_drift_report(mean_drift=0.6, collapse=True)
        score = self.r2.score_session(dissent, drift, quorum_confidence="High")
        self.assertEqual(score.grade, "suspicious")
        self.assertTrue(score.silent_collapse)
        self.assertTrue(any("Silent collapse" in f for f in score.flags))

    def test_suspicious_grade_high_agreement_high_drift(self):
        """High agreement + high NCG drift = suspicious even without collapse flag."""
        dissent = self._make_dissent_report(agreement=0.95)
        drift = self._make_drift_report(mean_drift=0.6, collapse=False)
        score = self.r2.score_session(dissent, drift, quorum_confidence="High")
        self.assertEqual(score.grade, "suspicious")
        self.assertTrue(any("Suspicious consensus" in f for f in score.flags))

    def test_weak_grade_no_quorum(self):
        """Low quorum confidence produces 'weak' grade."""
        dissent = self._make_dissent_report(agreement=0.5, dissent_level="moderate")
        score = self.r2.score_session(dissent, quorum_confidence="Low")
        self.assertEqual(score.grade, "weak")
        self.assertFalse(score.quorum_met)

    def test_weak_grade_high_dissent(self):
        """High dissent produces 'weak' grade."""
        dissent = self._make_dissent_report(agreement=0.3, dissent_level="high")
        drift = self._make_drift_report(mean_drift=0.2)
        score = self.r2.score_session(dissent, drift, quorum_confidence="High")
        self.assertEqual(score.grade, "weak")

    def test_acceptable_grade_with_outliers(self):
        """Outliers without other severe problems => 'acceptable'."""
        dissent = self._make_dissent_report(
            agreement=0.7, dissent_level="moderate",
            outlier_agents=["Prism"],
        )
        drift = self._make_drift_report(mean_drift=0.3)
        score = self.r2.score_session(dissent, drift, quorum_confidence="Medium")
        self.assertEqual(score.grade, "acceptable")
        self.assertTrue(score.has_outliers)

    def test_confidence_score_range(self):
        """Confidence score should always be between 0 and 1."""
        dissent = self._make_dissent_report(agreement=0.5)
        drift = self._make_drift_report(mean_drift=0.8, collapse=True)
        score = self.r2.score_session(dissent, drift, quorum_confidence="Low")
        self.assertGreaterEqual(score.confidence_score, 0.0)
        self.assertLessEqual(score.confidence_score, 1.0)

    def test_no_ncg_no_penalty(self):
        """When NCG is disabled, drift should be 0 with no penalty."""
        dissent = self._make_dissent_report(agreement=0.8)
        score = self.r2.score_session(dissent, drift_report=None,
                                      quorum_confidence="High")
        self.assertEqual(score.ncg_drift, 0.0)
        self.assertFalse(score.silent_collapse)

    # --- Signal detection tests ---

    def test_signals_silent_collapse(self):
        """Silent collapse should produce a critical suspicious_consensus signal."""
        dissent = self._make_dissent_report(agreement=0.95)
        drift = self._make_drift_report(collapse=True)
        score = self.r2.score_session(dissent, drift, quorum_confidence="High")
        signals = self.r2.detect_signals(score, dissent, drift)
        types = [s.signal_type for s in signals]
        self.assertIn("suspicious_consensus", types)
        critical = [s for s in signals if s.severity == "critical"]
        self.assertTrue(len(critical) >= 1)

    def test_signals_persistent_outlier(self):
        dissent = self._make_dissent_report(outlier_agents=["Prism"])
        score = self.r2.score_session(dissent, quorum_confidence="Medium")
        signals = self.r2.detect_signals(score, dissent)
        types = [s.signal_type for s in signals]
        self.assertIn("persistent_outlier", types)

    def test_signals_compression(self):
        dissent = self._make_dissent_report()
        drift = self._make_drift_report(compression=True)
        score = self.r2.score_session(dissent, drift, quorum_confidence="High")
        signals = self.r2.detect_signals(score, dissent, drift)
        types = [s.signal_type for s in signals]
        self.assertIn("compression", types)

    def test_signals_healthy_dissent(self):
        """High dissent without outliers = healthy dissent (info signal)."""
        dissent = self._make_dissent_report(
            agreement=0.3, dissent_level="high", outlier_agents=[],
        )
        score = self.r2.score_session(dissent, quorum_confidence="High")
        signals = self.r2.detect_signals(score, dissent)
        types = [s.signal_type for s in signals]
        self.assertIn("healthy_dissent", types)

    def test_signals_agent_degradation(self):
        """Weak grade + no quorum => agent_degradation signal."""
        dissent = self._make_dissent_report(agreement=0.5, dissent_level="moderate")
        score = self.r2.score_session(dissent, quorum_confidence="Low")
        signals = self.r2.detect_signals(score, dissent)
        types = [s.signal_type for s in signals]
        self.assertIn("agent_degradation", types)

    def test_no_signals_clean_session(self):
        """Strong session should produce no signals."""
        dissent = self._make_dissent_report(agreement=0.8, dissent_level="low")
        drift = self._make_drift_report(mean_drift=0.2)
        score = self.r2.score_session(dissent, drift, quorum_confidence="High")
        signals = self.r2.detect_signals(score, dissent, drift)
        self.assertEqual(len(signals), 0)

    # --- Ledger persistence tests ---

    def test_index_creates_file(self):
        dissent = self._make_dissent_report()
        score = self.r2.score_session(dissent, quorum_confidence="Medium")
        signals = self.r2.detect_signals(score, dissent)
        entry = self.r2.index(
            session_id="sess-123",
            prompt="test",
            consensus="merged answer",
            agents_agreed=["Sol", "Aria"],
            score=score,
            improvement_signals=signals,
            dissent_report=dissent,
        )
        self.assertTrue(len(entry.entry_id) > 0)
        self.assertEqual(self.r2.count(), 1)

    def test_index_and_load(self):
        dissent = self._make_dissent_report()
        score = self.r2.score_session(dissent, quorum_confidence="High")
        entry = self.r2.index(
            session_id="sess-456",
            prompt="test prompt",
            consensus="the consensus",
            agents_agreed=["Sol"],
            score=score,
            improvement_signals=[],
            dissent_report=dissent,
        )
        loaded = self.r2.load_entry(entry.entry_id)
        self.assertEqual(loaded["session_id"], "sess-456")
        self.assertEqual(loaded["consensus"], "the consensus")
        self.assertEqual(loaded["score"]["grade"], score.grade)

    def test_list_entries(self):
        dissent = self._make_dissent_report()
        for i in range(3):
            score = self.r2.score_session(dissent, quorum_confidence="High")
            self.r2.index(
                session_id=f"sess-{i}",
                prompt=f"prompt {i}",
                consensus="answer",
                agents_agreed=["Sol"],
                score=score,
                improvement_signals=[],
                dissent_report=dissent,
            )
        summaries = self.r2.list_entries(limit=10)
        self.assertEqual(len(summaries), 3)
        self.assertIn("entry_id", summaries[0])
        self.assertIn("grade", summaries[0])

    # --- Trend analysis tests ---

    def test_trend_analysis_insufficient_data(self):
        result = self.r2.analyze_ledger_trends()
        self.assertEqual(result["entries_analyzed"], 0)
        self.assertEqual(result["trends"], [])

    def test_trend_analysis_with_data(self):
        dissent = self._make_dissent_report()
        for i in range(5):
            score = self.r2.score_session(dissent, quorum_confidence="High")
            self.r2.index(
                session_id=f"sess-{i}",
                prompt=f"prompt {i}",
                consensus="answer",
                agents_agreed=["Sol", "Aria"],
                score=score,
                improvement_signals=[],
                dissent_report=dissent,
            )
        result = self.r2.analyze_ledger_trends(limit=10)
        self.assertEqual(result["entries_analyzed"], 5)
        self.assertGreater(result["mean_confidence"], 0.0)
        self.assertIn("grade_distribution", result)


class TestR2Integration(unittest.TestCase):
    """Verify R2 data flows through the orchestrator output."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._r2_tmpdir = tempfile.mkdtemp()
        # Patch storage dirs so tests don't pollute real data
        import maestro.session as session_mod
        import maestro.r2 as r2_mod
        self._original_session_dir = session_mod._DEFAULT_DIR
        self._original_r2_dir = r2_mod._DEFAULT_LEDGER_DIR
        session_mod._DEFAULT_DIR = __import__("pathlib").Path(self._tmpdir)
        r2_mod._DEFAULT_LEDGER_DIR = __import__("pathlib").Path(self._r2_tmpdir)

    def tearDown(self):
        import maestro.session as session_mod
        import maestro.r2 as r2_mod
        session_mod._DEFAULT_DIR = self._original_session_dir
        r2_mod._DEFAULT_LEDGER_DIR = self._original_r2_dir
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        shutil.rmtree(self._r2_tmpdir, ignore_errors=True)

    def test_r2_in_final_output(self):
        result = run_orchestration("test prompt", session_logging=True)
        final = result["final_output"]
        self.assertIn("r2", final)

        r2 = final["r2"]
        self.assertIn("grade", r2)
        self.assertIn("confidence_score", r2)
        self.assertIn("flags", r2)
        self.assertIn("signal_count", r2)
        self.assertIn("entry_id", r2)

        self.assertIn(r2["grade"], ("strong", "acceptable", "weak", "suspicious"))
        self.assertGreaterEqual(r2["confidence_score"], 0.0)
        self.assertLessEqual(r2["confidence_score"], 1.0)

    def test_r2_creates_ledger_entry(self):
        result = run_orchestration("test prompt", session_logging=True)
        r2_engine = R2Engine(ledger_dir=self._r2_tmpdir)
        self.assertEqual(r2_engine.count(), 1)

        entry_id = result["final_output"]["r2"]["entry_id"]
        loaded = r2_engine.load_entry(entry_id)
        self.assertEqual(loaded["prompt"], "test prompt")

    def test_r2_without_session_logging(self):
        """R2 should still produce scores even with session logging off."""
        result = run_orchestration("test prompt", session_logging=False)
        self.assertIn("r2", result["final_output"])
        self.assertIn("grade", result["final_output"]["r2"])


class TestMagi(unittest.TestCase):
    """Verify MAGI cross-session analysis and recommendation generation."""

    def setUp(self):
        self._r2_dir = tempfile.mkdtemp()
        self._session_dir = tempfile.mkdtemp()
        self.r2 = R2Engine(ledger_dir=self._r2_dir)
        from maestro.session import SessionLogger
        self.session_logger = SessionLogger(storage_dir=self._session_dir)

    def tearDown(self):
        shutil.rmtree(self._r2_dir, ignore_errors=True)
        shutil.rmtree(self._session_dir, ignore_errors=True)

    def _populate_ledger(self, count=5, outlier_agents=None, collapse=False,
                         dissent_level="low", agreement=0.8):
        """Add entries to the R2 ledger for testing."""
        for i in range(count):
            dissent = DissentReport(
                prompt=f"prompt {i}",
                internal_agreement=agreement,
                pairwise=[],
                agent_profiles=[],
                outlier_agents=outlier_agents or [],
                dissent_level=dissent_level,
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

    def test_empty_analysis(self):
        """MAGI should handle empty ledger gracefully."""
        from maestro.magi import Magi
        magi = Magi(r2=self.r2, session_logger=self.session_logger)
        report = magi.analyze()
        self.assertEqual(report.ledger_entries_analyzed, 0)
        self.assertEqual(report.confidence_trend, "stable")

    def test_healthy_system(self):
        """A healthy ledger should produce positive recommendations."""
        self._populate_ledger(count=5, collapse=False, agreement=0.8)
        from maestro.magi import Magi
        magi = Magi(r2=self.r2, session_logger=self.session_logger)
        report = magi.analyze()
        self.assertEqual(report.ledger_entries_analyzed, 5)
        self.assertEqual(report.collapse_frequency, 0.0)
        # Should have at least the "no silent collapse" positive signal
        positive = [r for r in report.recommendations if r.category == "positive"]
        self.assertTrue(len(positive) >= 1)

    def test_persistent_outlier_recommendation(self):
        """An agent that is always an outlier should trigger a recommendation."""
        self._populate_ledger(count=5, outlier_agents=["Prism"])
        from maestro.magi import Magi
        magi = Magi(r2=self.r2, session_logger=self.session_logger)
        report = magi.analyze()
        self.assertGreater(report.agent_health["Prism"]["outlier_rate"], 0.5)
        agent_recs = [r for r in report.recommendations if r.category == "agent"]
        self.assertTrue(len(agent_recs) >= 1)
        self.assertIn("Prism", agent_recs[0].affected_agents)

    def test_frequent_collapse_recommendation(self):
        """Frequent silent collapses should trigger a critical recommendation."""
        self._populate_ledger(count=5, collapse=True, agreement=0.95)
        from maestro.magi import Magi
        magi = Magi(r2=self.r2, session_logger=self.session_logger)
        report = magi.analyze()
        self.assertGreater(report.collapse_frequency, 0.3)
        critical = [r for r in report.recommendations if r.severity == "critical"]
        self.assertTrue(len(critical) >= 1)

    def test_report_fields(self):
        """Verify all expected fields are present in the MAGI report."""
        self._populate_ledger(count=3)
        from maestro.magi import Magi, MagiReport
        magi = Magi(r2=self.r2, session_logger=self.session_logger)
        report = magi.analyze()
        self.assertIsInstance(report, MagiReport)
        self.assertIn(report.confidence_trend, ("improving", "declining", "stable"))
        self.assertIsInstance(report.mean_confidence, float)
        self.assertIsInstance(report.grade_distribution, dict)
        self.assertIsInstance(report.agent_health, dict)
        self.assertIsInstance(report.recommendations, list)


if __name__ == "__main__":
    unittest.main()
