#!/usr/bin/env python3
"""
Maestro-Orchestrator Interactive CLI.

Provides a terminal-based REPL for sending prompts through the full
orchestration pipeline (agents, dissent, NCG, R2, session logging)
and viewing results directly in the console.

Usage (standalone):
    python -m maestro.cli

Usage (from entrypoint):
    Called by entrypoint.py when the user selects "CLI" mode.
"""

import asyncio
import os
import sys
import textwrap

# ---------------------------------------------------------------------------
# Path bootstrap — ensure the backend and project root are importable
# ---------------------------------------------------------------------------
_here = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_here)
_backend_dir = os.path.join(_project_root, "backend")

for p in (_project_root, _backend_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv

# Load .env using the same logic as orchestrator_foundry.py
_dotenv_path = os.environ.get("MAESTRO_ENV_FILE") or os.path.join(_backend_dir, ".env")
load_dotenv(dotenv_path=_dotenv_path)

from maestro.agents.sol import Sol
from maestro.agents.aria import Aria
from maestro.agents.prism import Prism
from maestro.agents.tempagent import TempAgent
from maestro.orchestrator import run_orchestration_async
from maestro.ncg.generator import (
    OpenAIHeadlessGenerator,
    AnthropicHeadlessGenerator,
    MockHeadlessGenerator,
)

# ---------------------------------------------------------------------------
# Council (same roster as orchestrator_foundry.py)
# ---------------------------------------------------------------------------
COUNCIL = [Sol(), Aria(), Prism(), TempAgent()]


def _select_headless_generator():
    """Pick the best available headless generator based on API keys."""
    if os.getenv("OPENAI_API_KEY"):
        return OpenAIHeadlessGenerator()
    if os.getenv("ANTHROPIC_API_KEY"):
        return AnthropicHeadlessGenerator()
    return MockHeadlessGenerator()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
SEPARATOR = "-" * 60
THIN_SEP = "-" * 40

_GRADE_ICONS = {
    "strong": "[STRONG]",
    "acceptable": "[ACCEPTABLE]",
    "weak": "[WEAK]",
    "suspicious": "[SUSPICIOUS]",
}


def _wrap(text: str, width: int = 72, indent: str = "    ") -> str:
    """Word-wrap text with a hanging indent."""
    return textwrap.fill(text, width=width, initial_indent=indent,
                         subsequent_indent=indent)


def _print_banner():
    print()
    print("=" * 60)
    print("  Maestro-Orchestrator  —  Interactive CLI")
    print("=" * 60)
    print()
    print("  Type a prompt and press Enter to run the full pipeline.")
    print("  Commands:")
    print("    /keys     — show API key status")
    print("    /help     — show this help text")
    print("    /quit     — exit the CLI")
    print()


def _print_result(result: dict):
    """Pretty-print an orchestration result to the terminal."""
    named = result.get("named_responses", {})
    final = result.get("final_output", {})
    session_id = result.get("session_id")

    # --- Agent responses ---
    print()
    print(SEPARATOR)
    print("  Agent Responses")
    print(SEPARATOR)
    for name, response in named.items():
        print(f"\n  [{name}]")
        print(_wrap(response))

    # --- Consensus ---
    print()
    print(SEPARATOR)
    print("  Consensus")
    print(SEPARATOR)
    consensus = final.get("consensus", "N/A")
    confidence = final.get("confidence", "N/A")
    ratio = final.get("agreement_ratio")
    quorum_met = final.get("quorum_met")
    print(f"  Confidence : {confidence}")
    if ratio is not None:
        print(f"  Agreement  : {ratio:.0%}")
    if quorum_met is not None:
        print(f"  Quorum met : {'Yes' if quorum_met else 'No'}")
    print()
    print(_wrap(consensus))

    # --- Dissent ---
    dissent = final.get("dissent")
    if dissent:
        print()
        print(THIN_SEP)
        print("  Dissent")
        print(THIN_SEP)
        print(f"  Internal agreement : {dissent.get('internal_agreement', 'N/A')}")
        print(f"  Dissent level      : {dissent.get('dissent_level', 'N/A')}")
        outliers = dissent.get("outlier_agents", [])
        if outliers:
            print(f"  Outlier agents     : {', '.join(outliers)}")

    # --- NCG benchmark ---
    ncg = final.get("ncg_benchmark")
    if ncg:
        print()
        print(THIN_SEP)
        print("  NCG Benchmark")
        print(THIN_SEP)
        print(f"  Model          : {ncg.get('ncg_model', 'N/A')}")
        print(f"  Mean drift     : {ncg.get('mean_drift', 'N/A')}")
        collapse = ncg.get("silent_collapse", False)
        print(f"  Silent collapse: {'YES' if collapse else 'No'}")

    # --- R2 ---
    r2 = final.get("r2")
    if r2:
        print()
        print(THIN_SEP)
        print("  R2 Score")
        print(THIN_SEP)
        grade = r2.get("grade", "N/A")
        icon = _GRADE_ICONS.get(grade, "")
        print(f"  Grade      : {grade}  {icon}")
        print(f"  Confidence : {r2.get('confidence_score', 'N/A')}")
        flags = r2.get("flags", [])
        if flags:
            for f in flags:
                print(f"  Flag       : {f}")
        signals = r2.get("signal_count", 0)
        if signals:
            print(f"  Signals    : {signals} improvement recommendation(s)")

    # --- Session ---
    if session_id:
        print()
        print(f"  Session ID : {session_id}")

    print()
    print(SEPARATOR)
    print()


def _print_keys():
    """Show API key configuration status."""
    from maestro.keyring import list_keys

    statuses = list_keys()
    print()
    print(f"  {'Provider':<14} {'Status':<14} {'Key'}")
    print(f"  {'--------':<14} {'------':<14} {'---'}")
    for s in statuses:
        status_str = "configured" if s.configured else "missing"
        key_str = s.masked_value if s.configured else "-"
        print(f"  {s.label:<14} {status_str:<14} {key_str}")
    print()


# ---------------------------------------------------------------------------
# Main interactive loop
# ---------------------------------------------------------------------------

def interactive_loop():
    """REPL-style prompt loop that runs the full orchestration pipeline."""
    _print_banner()

    while True:
        try:
            user_input = input("maestro> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[Maestro] Goodbye.")
            break

        if not user_input:
            continue

        lower = user_input.lower()

        if lower in ("/quit", "/exit", "/q"):
            print("[Maestro] Goodbye.")
            break

        if lower in ("/help", "/h", "/?"):
            _print_banner()
            continue

        if lower in ("/keys", "/key"):
            _print_keys()
            continue

        # --- Run orchestration ---
        print(f"\n[Maestro] Orchestrating: {user_input[:80]}{'...' if len(user_input) > 80 else ''}")
        try:
            result = asyncio.run(
                run_orchestration_async(
                    prompt=user_input,
                    agents=COUNCIL,
                    ncg_enabled=True,
                    session_logging=True,
                    headless_generator=_select_headless_generator(),
                )
            )
            _print_result(result)
        except Exception as e:
            print(f"\n[ERROR] Orchestration failed: {e}\n")


# ---------------------------------------------------------------------------
# Standalone entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    interactive_loop()
