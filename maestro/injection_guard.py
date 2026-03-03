"""
Injection Guard — safety rails for the code injection system.

Ensures that auto-injection never runs wild:

  1. Category whitelist   — only approved proposal categories can be injected
  2. Bounds enforcement   — re-validates min/max at injection time
  3. Rate limiting        — caps injections per hour
  4. Smoke test           — quick benchmark after injection; auto-rollback on degradation
  5. Opt-in gate          — entire system disabled unless explicitly enabled
"""

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from maestro.optimization import OptimizationProposal


# Re-export the strategy bounds from optimization.py so the guard can
# validate without duplicating the numbers.
from maestro.optimization import _THRESHOLD_STRATEGIES, _TEMPERATURE_STRATEGIES


_DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "data" / "runtime_config.json"

# Categories that may be auto-injected without human review.
_DEFAULT_INJECTABLE = {"threshold", "agent_config", "token_tuning"}
_DEFAULT_BLOCKED = {"architecture", "pipeline"}

_DEFAULT_MAX_INJECTIONS_PER_HOUR = 5
_DEFAULT_SMOKE_TEST_MIN_GRADE = "acceptable"
_GRADE_RANK = {"suspicious": 0, "weak": 1, "acceptable": 2, "strong": 3}


@dataclass
class GuardConfig:
    """Runtime-configurable guard settings."""
    auto_inject_enabled: bool = False
    max_injections_per_hour: int = _DEFAULT_MAX_INJECTIONS_PER_HOUR
    injectable_categories: set = field(default_factory=lambda: set(_DEFAULT_INJECTABLE))
    blocked_categories: set = field(default_factory=lambda: set(_DEFAULT_BLOCKED))
    smoke_test_prompts: list = field(default_factory=lambda: ["What is consciousness?"])
    smoke_test_min_grade: str = _DEFAULT_SMOKE_TEST_MIN_GRADE


class InjectionGuard:
    """
    Validates proposals before injection and runs post-injection smoke tests.

    The guard is the single chokepoint between "VIR says promote" and
    "the system actually changes".  Every safety check lives here.
    """

    def __init__(self, config: GuardConfig = None):
        self._config = config or GuardConfig()
        # Track injection timestamps for rate limiting
        self._injection_timestamps: list[float] = []

    @property
    def config(self) -> GuardConfig:
        return self._config

    # --- opt-in gate ---

    def is_enabled(self) -> bool:
        """Check whether auto-injection is enabled.

        Reads both the GuardConfig and the ``MAESTRO_AUTO_INJECT``
        environment variable.  Either one being true is sufficient.
        """
        env = os.environ.get("MAESTRO_AUTO_INJECT", "").lower()
        return self._config.auto_inject_enabled or env in ("true", "1", "yes")

    # --- per-proposal checks ---

    def is_injectable(self, proposal: OptimizationProposal) -> tuple:
        """
        Returns (allowed: bool, reason: str).

        Checks category whitelist and bounds.
        """
        if proposal.category in self._config.blocked_categories:
            return False, f"Category '{proposal.category}' is blocked from auto-injection"

        if proposal.category not in self._config.injectable_categories:
            return False, f"Category '{proposal.category}' is not in the injectable whitelist"

        if proposal.status not in ("validated", "proposed"):
            return False, f"Proposal status '{proposal.status}' is not injectable"

        if not self.check_bounds(proposal):
            return False, "Proposed value is outside allowed bounds"

        return True, "ok"

    def check_bounds(self, proposal: OptimizationProposal) -> bool:
        """Verify the proposed value is within the strategy min/max bounds."""
        if proposal.change_type != "parameter_update":
            return True  # bounds only apply to numeric updates

        try:
            proposed = float(proposal.proposed_value)
        except (ValueError, TypeError):
            return True  # non-numeric, bounds check doesn't apply

        # Check threshold bounds
        strategies = _THRESHOLD_STRATEGIES.get(proposal.target_name, {})
        for strategy in strategies.values():
            if proposed < strategy["min_val"] or proposed > strategy["max_val"]:
                return False

        # Check temperature bounds
        if proposal.target_name == "temperature":
            for strategy in _TEMPERATURE_STRATEGIES.values():
                if proposed < strategy["min_val"] or proposed > strategy["max_val"]:
                    return False

        return True

    # --- rate limiting ---

    def check_rate_limit(self) -> bool:
        """Returns True if injection is allowed under the rate limit."""
        now = time.monotonic()
        cutoff = now - 3600  # one hour window
        self._injection_timestamps = [
            t for t in self._injection_timestamps if t > cutoff
        ]
        return len(self._injection_timestamps) < self._config.max_injections_per_hour

    def record_injection(self):
        """Record that an injection just happened (for rate limiting)."""
        self._injection_timestamps.append(time.monotonic())

    # --- smoke test ---

    def smoke_test(self) -> tuple:
        """
        Run a quick benchmark after injection to verify the system
        didn't degrade.

        Returns (passed: bool, grade: str).
        """
        from maestro.aggregator import aggregate_responses
        from maestro.dissent import DissentAnalyzer
        from maestro.ncg.generator import MockHeadlessGenerator
        from maestro.ncg.drift import DriftDetector
        from maestro.r2 import R2Engine

        prompt = self._config.smoke_test_prompts[0]

        # Run a minimal pipeline with mock agents
        named_responses = {
            "SmokeAgent1": f"[SmokeAgent1] Considering '{prompt}' from multiple angles.",
            "SmokeAgent2": f"[SmokeAgent2] Analyzing '{prompt}' with a systems perspective.",
            "SmokeAgent3": f"[SmokeAgent3] Reflecting on '{prompt}' philosophically.",
        }

        dissent_analyzer = DissentAnalyzer()
        dissent_report = dissent_analyzer.analyze(prompt, named_responses)

        generator = MockHeadlessGenerator()
        ncg_output = generator.generate(prompt)
        detector = DriftDetector()
        drift_report = detector.analyze(
            prompt=prompt,
            ncg_output=ncg_output,
            conversational_outputs=named_responses,
            internal_agreement=dissent_report.internal_agreement,
        )

        final_output = aggregate_responses(
            list(named_responses.values()), drift_report, dissent_report,
        )

        r2 = R2Engine()
        r2_score = r2.score_session(
            dissent_report=dissent_report,
            drift_report=drift_report,
            quorum_confidence=final_output.get("confidence", "Low"),
        )

        min_rank = _GRADE_RANK.get(self._config.smoke_test_min_grade, 2)
        actual_rank = _GRADE_RANK.get(r2_score.grade, -1)

        passed = actual_rank >= min_rank
        return passed, r2_score.grade
