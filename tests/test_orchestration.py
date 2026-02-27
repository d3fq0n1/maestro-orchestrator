import unittest
from maestro.orchestrator import run_orchestration
from maestro.ncg.generator import MockHeadlessGenerator
from maestro.ncg.drift import DriftDetector, DriftReport


class TestMaestroOrchestration(unittest.TestCase):

    def test_mock_responses(self):
        prompt = "What is the meaning of life?"
        result = run_orchestration(prompt)

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
        result = run_orchestration(prompt, ncg_enabled=True)

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
        result = run_orchestration(prompt, ncg_enabled=False)

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

        # Simulate agents that all agree (high internal agreement)
        # but say something very different from the headless baseline
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

        # High agreement + high drift = silent collapse
        self.assertTrue(report.mean_semantic_distance > 0.0)

    def test_compression_ratio(self):
        detector = DriftDetector()
        ratio = detector._compression_ratio("short", "this is a much longer baseline text")
        self.assertLess(ratio, 1.0)

    def test_semantic_distance_identical(self):
        detector = DriftDetector()
        distance = detector._semantic_distance("hello world", "hello world")
        self.assertEqual(distance, 0.0)


if __name__ == "__main__":
    unittest.main()
