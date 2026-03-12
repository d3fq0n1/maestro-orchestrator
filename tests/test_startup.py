"""
Tests for the unified startup wrapper (entrypoint.py) and the
interactive CLI module (maestro/cli.py).
"""

import asyncio
import io
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

# Ensure project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ── entrypoint.py tests ──────────────────────────────────────────────


class TestEntrypointDialogDetection(unittest.TestCase):
    """Verify dialog availability detection."""

    def test_dialog_available_returns_bool(self):
        from entrypoint import _dialog_available
        result = _dialog_available()
        self.assertIsInstance(result, bool)

    @patch("entrypoint.subprocess.run", side_effect=FileNotFoundError)
    def test_dialog_not_found(self, _mock_run):
        from entrypoint import _dialog_available
        self.assertFalse(_dialog_available())


class TestEntrypointPlainPrompt(unittest.TestCase):
    """Verify the plain-text fallback prompt (via interactive selector)."""

    @patch("builtins.input", return_value="1")
    def test_plain_prompt_tui(self, _mock_input):
        from entrypoint import _plain_prompt
        # Option 1 is TUI in the selector
        self.assertEqual(_plain_prompt(), "tui")

    @patch("builtins.input", return_value="2")
    def test_plain_prompt_cli(self, _mock_input):
        from entrypoint import _plain_prompt
        self.assertEqual(_plain_prompt(), "cli")

    @patch("builtins.input", return_value="3")
    def test_plain_prompt_web(self, _mock_input):
        from entrypoint import _plain_prompt
        self.assertEqual(_plain_prompt(), "web")

    @patch("builtins.input", return_value="")
    def test_plain_prompt_default(self, _mock_input):
        from entrypoint import _plain_prompt
        # Default is first option (TUI)
        self.assertEqual(_plain_prompt(), "tui")

    @patch("builtins.input", side_effect=EOFError)
    def test_plain_prompt_eof(self, _mock_input):
        from entrypoint import _plain_prompt
        # Default to first option on EOF
        self.assertEqual(_plain_prompt(), "tui")

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_plain_prompt_ctrl_c(self, _mock_input):
        from entrypoint import _plain_prompt
        # Default to first option on Ctrl+C
        self.assertEqual(_plain_prompt(), "tui")


class TestEntrypointEnvOverride(unittest.TestCase):
    """MAESTRO_MODE environment variable should bypass the dialog."""

    @patch("entrypoint.launch_web")
    def test_env_mode_web(self, mock_launch):
        with patch.dict(os.environ, {"MAESTRO_MODE": "web"}):
            from entrypoint import main
            main()
        mock_launch.assert_called_once()

    @patch("entrypoint.launch_cli")
    def test_env_mode_cli(self, mock_launch):
        with patch.dict(os.environ, {"MAESTRO_MODE": "cli"}):
            from entrypoint import main
            main()
        mock_launch.assert_called_once()


class TestEntrypointNoTTY(unittest.TestCase):
    """When stdin is not a TTY, default to web without prompting."""

    @patch("entrypoint.launch_web")
    @patch("sys.stdin")
    def test_no_tty_defaults_to_web(self, mock_stdin, mock_launch):
        mock_stdin.isatty.return_value = False
        with patch.dict(os.environ, {}, clear=False):
            # Remove MAESTRO_MODE if present
            os.environ.pop("MAESTRO_MODE", None)
            from entrypoint import main
            main()
        mock_launch.assert_called_once()


# ── maestro/cli.py tests ─────────────────────────────────────────────


class TestCLIFormatting(unittest.TestCase):
    """Verify CLI output helpers."""

    def test_wrap_helper(self):
        from maestro.cli import _wrap
        result = _wrap("Hello world, this is a test string.")
        self.assertIsInstance(result, str)
        self.assertIn("Hello", result)

    def test_grade_icons(self):
        from maestro.cli import _GRADE_ICONS
        self.assertIn("strong", _GRADE_ICONS)
        self.assertIn("suspicious", _GRADE_ICONS)


class TestCLIPrintResult(unittest.TestCase):
    """Verify _print_result doesn't crash on various payloads."""

    def _capture_print(self, result):
        from maestro.cli import _print_result
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            _print_result(result)
        return buf.getvalue()

    def test_minimal_result(self):
        output = self._capture_print({
            "named_responses": {"MockAgent": "test response"},
            "final_output": {"consensus": "agreed"},
        })
        self.assertIn("MockAgent", output)
        self.assertIn("agreed", output)

    def test_full_result(self):
        output = self._capture_print({
            "named_responses": {"Sol": "resp1", "Aria": "resp2"},
            "final_output": {
                "consensus": "merged",
                "confidence": "High",
                "agreement_ratio": 0.85,
                "quorum_met": True,
                "dissent": {
                    "internal_agreement": 0.9,
                    "dissent_level": "low",
                    "outlier_agents": [],
                },
                "ncg_benchmark": {
                    "ncg_model": "mock-v1",
                    "mean_drift": 0.3,
                    "silent_collapse": False,
                },
                "r2": {
                    "grade": "strong",
                    "confidence_score": 0.82,
                    "flags": [],
                    "signal_count": 0,
                },
            },
            "session_id": "test-session-123",
        })
        self.assertIn("Sol", output)
        self.assertIn("Aria", output)
        self.assertIn("strong", output)
        self.assertIn("85%", output)
        self.assertIn("test-session-123", output)

    def test_result_with_flags(self):
        output = self._capture_print({
            "named_responses": {},
            "final_output": {
                "consensus": "none",
                "r2": {
                    "grade": "suspicious",
                    "confidence_score": 0.3,
                    "flags": ["Silent collapse detected"],
                    "signal_count": 2,
                },
            },
        })
        self.assertIn("suspicious", output)
        self.assertIn("Silent collapse detected", output)


class TestCLIInteractiveLoop(unittest.TestCase):
    """Verify the REPL handles commands and exits gracefully."""

    @patch("builtins.input", side_effect=["/quit"])
    def test_quit_command(self, _mock_input):
        from maestro.cli import interactive_loop
        # Should exit without error
        interactive_loop()

    @patch("builtins.input", side_effect=["/exit"])
    def test_exit_command(self, _mock_input):
        from maestro.cli import interactive_loop
        interactive_loop()

    @patch("builtins.input", side_effect=EOFError)
    def test_eof_exits(self, _mock_input):
        from maestro.cli import interactive_loop
        interactive_loop()

    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_ctrl_c_exits(self, _mock_input):
        from maestro.cli import interactive_loop
        interactive_loop()

    @patch("builtins.input", side_effect=["", "/q"])
    def test_empty_input_ignored(self, _mock_input):
        from maestro.cli import interactive_loop
        interactive_loop()

    @patch("builtins.input", side_effect=["/help", "/quit"])
    def test_help_command(self, _mock_input):
        from maestro.cli import interactive_loop
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            interactive_loop()
        output = buf.getvalue()
        self.assertIn("Interactive CLI", output)

    @patch("builtins.input", side_effect=["/keys", "/quit"])
    def test_keys_command(self, _mock_input):
        from maestro.cli import interactive_loop
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            interactive_loop()
        output = buf.getvalue()
        self.assertIn("Provider", output)


class TestCLIOrchestration(unittest.TestCase):
    """Verify prompts route through the orchestration pipeline."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._r2_tmpdir = tempfile.mkdtemp()
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

    @patch("builtins.input", side_effect=["test prompt", "/quit"])
    @patch("maestro.cli.COUNCIL", [])
    def test_prompt_runs_orchestration(self, _mock_input):
        """A typed prompt should trigger orchestration and print results."""
        # Patch COUNCIL to use mock agents
        from maestro.agents.mock import MockAgent
        import maestro.cli as cli_mod
        cli_mod.COUNCIL = [
            MockAgent(name="MockA", response_style="neutral"),
            MockAgent(name="MockB", response_style="empathic"),
        ]

        buf = io.StringIO()
        with patch("sys.stdout", buf):
            cli_mod.interactive_loop()

        output = buf.getvalue()
        self.assertIn("MockA", output)
        self.assertIn("MockB", output)
        self.assertIn("Consensus", output)


if __name__ == "__main__":
    unittest.main()
