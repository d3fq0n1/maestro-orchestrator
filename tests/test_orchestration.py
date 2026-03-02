import asyncio
import os
import shutil
import tempfile
import unittest
from maestro.orchestrator import run_orchestration
from maestro.agents import Agent, MockAgent, Sol, Aria, Prism, TempAgent
from maestro.ncg.generator import MockHeadlessGenerator
from maestro.ncg.drift import DriftDetector, DriftReport
from maestro.session import SessionLogger, SessionRecord, build_session_record


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


if __name__ == "__main__":
    unittest.main()
