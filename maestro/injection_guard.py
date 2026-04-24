"""
Injection Guard — safety rails for both code-injection and prompt-injection.

This module owns the "injection" family of safety functions:

  A. Code-injection rails (the ``InjectionGuard`` class).
     Gates the self-improvement auto-apply pipeline:
       1. Category whitelist   — only approved proposal categories can be injected
       2. Bounds enforcement   — re-validates min/max at injection time
       3. Rate limiting        — caps injections per hour
       4. Smoke test           — quick benchmark after injection; auto-rollback
       5. Opt-in gate          — entire system disabled unless explicitly enabled

  B. Prompt-injection sentinels (module-level functions).
     Sanitises untrusted text (bundle manifest abstracts, tool outputs,
     user-supplied fragments) before it reaches a specialist's prompt:
       * ``sanitize_untrusted_text``  — strip/escape instruction-shaped
         content, collapse whitespace, cap length.
       * ``detect_injection_patterns`` — return a structured report of
         suspicious patterns without mutating the text.
       * ``wrap_untrusted``            — fence text inside an explicit
         UNTRUSTED delimiter block with a per-call nonce so nested content
         cannot forge the closing fence.

These two halves share the name "injection" but nothing else — the split is
intentional: both are safety rails, both live at this module, neither depends
on the other. Future sentinel/sanitation helpers in this family belong here.
"""

import os
import re
import secrets
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
_DEFAULT_INJECTABLE = {"threshold", "agent_config", "token_tuning", "storage", "module"}
_DEFAULT_BLOCKED = {"architecture", "pipeline", "shard_eviction"}

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


# ---------------------------------------------------------------------------
# Prompt-injection sentinels
# ---------------------------------------------------------------------------
#
# These functions protect specialist prompts from untrusted text (bundle
# manifest abstracts, tool outputs, attacker-controlled fragments). They are
# stateless, side-effect free, and deliberately conservative: false positives
# are preferable to letting an instruction-shaped payload slip through.
# ---------------------------------------------------------------------------

# Patterns that look like instruction-injection attempts. These catch the
# common shapes — role markers, system-prompt spoofing, fenced instructions,
# tool-call forgery, and trailing-instruction escapes. Extend deliberately:
# each pattern here will also cause real prose to be redacted, so keep
# them narrow.
_INJECTION_PATTERNS: list[tuple[str, str]] = [
    # Role / system spoofing
    ("role_marker", r"(?im)^\s*(?:system|assistant|user|developer)\s*[:>]"),
    ("system_override", r"(?i)\b(?:ignore|disregard|forget)\b[^\n]{0,60}\b(?:previous|prior|above|earlier)\b"),
    ("new_instructions", r"(?i)\b(?:new|updated|override)\s+instructions?\b"),
    # Prompt-boundary forgery
    ("closing_fence", r"(?m)^-{3,}\s*$"),
    ("xml_prompt_tag", r"(?i)</?(?:system|instructions|prompt|assistant)(?:\s+[^>]*)?>"),
    # Tool / action forgery
    ("tool_call", r"(?i)<\s*tool_use|<\s*invoke|<\s*function_calls"),
    ("shell_prompt", r"(?m)^\s*(?:\$|#)\s"),
    # Data-exfil primitives
    ("url_exfil", r"(?i)https?://[^\s<>\"']{0,200}(?:\?|&)[a-z0-9_]+=[^\s]"),
]

_SENTINEL_REDACTION = "[REDACTED:INJECTION]"
_MAX_UNTRUSTED_CHARS = 4000  # hard cap on sanitised text length
_MAX_NEWLINES_RUN = 2        # collapse 3+ blank lines to 2


def detect_injection_patterns(text: str) -> dict:
    """Report suspicious patterns in ``text`` without modifying it.

    Returns a dict of {pattern_name: [match_snippets]}. Empty dict means
    nothing matched. Snippets are truncated to 80 chars.
    """
    if not text:
        return {}
    hits: dict[str, list[str]] = {}
    for name, pattern in _INJECTION_PATTERNS:
        matches = re.findall(pattern, text)
        if not matches:
            continue
        snippets: list[str] = []
        for m in matches[:5]:
            snippet = m if isinstance(m, str) else " ".join(m)
            snippets.append(snippet[:80])
        hits[name] = snippets
    return hits


def sanitize_untrusted_text(
    text: str,
    max_chars: int = _MAX_UNTRUSTED_CHARS,
) -> str:
    """Return a scrubbed version of ``text`` safe to embed in a prompt.

    Applied transformations, in order:
      1. Redact anything matching an injection pattern.
      2. Strip zero-width / bidi-override control characters.
      3. Collapse runs of blank lines to at most ``_MAX_NEWLINES_RUN``.
      4. Trim to ``max_chars``, breaking at the last whitespace boundary.

    The function is idempotent: sanitising already-sanitised text is a
    no-op.
    """
    if not text:
        return ""

    scrubbed = text
    for _name, pattern in _INJECTION_PATTERNS:
        scrubbed = re.sub(pattern, _SENTINEL_REDACTION, scrubbed)

    # Remove zero-width / bidi-override chars commonly used for hiding
    # payloads inside visually-plain text.
    scrubbed = re.sub(r"[​-‏‪-‮⁠-⁯]", "", scrubbed)

    # Collapse excessive blank lines.
    scrubbed = re.sub(r"\n{3,}", "\n" * _MAX_NEWLINES_RUN, scrubbed)

    scrubbed = scrubbed.strip()

    if len(scrubbed) > max_chars:
        truncated = scrubbed[:max_chars]
        if " " in truncated:
            truncated = truncated.rsplit(" ", 1)[0]
        scrubbed = truncated + "…"

    return scrubbed


def wrap_untrusted(text: str, label: str = "UNTRUSTED") -> str:
    """Fence untrusted text inside an unforgeable delimiter block.

    A per-call random nonce is woven into the fence so nested content
    cannot close the block prematurely. The caller shows the model the
    opening + closing fences in its prompt template.

    The returned block is plain text, safe to concatenate into a prompt.
    """
    nonce = secrets.token_hex(8)
    open_fence = f"<<<{label}:{nonce}>>>"
    close_fence = f"<<<END:{nonce}>>>"

    # Defensive: strip any occurrence of our own fence shape from the payload
    # so even a sanitised body cannot forge one by accident.
    cleaned = re.sub(r"<<<[A-Z_]+:[a-f0-9]+>>>", _SENTINEL_REDACTION, text or "")
    return f"{open_fence}\n{cleaned}\n{close_fence}"
