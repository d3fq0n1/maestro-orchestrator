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
    print("    /keys       — show API key status")
    print("    /improve    — run a self-improvement cycle")
    print("    /introspect — analyze code for optimization targets")
    print("    /cycles     — show recent improvement cycles")
    print("    /update     — check for and apply updates")
    print("    /help       — show this help text")
    print("    /quit       — exit the CLI")
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
# Self-improvement commands
# ---------------------------------------------------------------------------

def _run_improvement_cycle():
    """Run a full self-improvement cycle and display results."""
    from maestro.self_improve import SelfImprovementEngine

    print()
    print(SEPARATOR)
    print("  Self-Improvement Cycle")
    print(SEPARATOR)
    print("  Running: MAGI analysis -> Introspect -> Propose -> Validate")
    print()

    try:
        engine = SelfImprovementEngine()
        cycle = engine.run_cycle()

        print(f"  Cycle ID    : {cycle.cycle_id}")
        print(f"  Phase       : {cycle.phase}")
        print(f"  Outcome     : {cycle.outcome}")
        print(f"  Proposals   : {cycle.proposal_count}")
        print(f"  Duration    : {cycle.duration_ms}ms")
        print(f"  Compute node: {cycle.compute_node}")

        if cycle.magi_report:
            report = cycle.magi_report
            print()
            print(THIN_SEP)
            print("  MAGI Analysis")
            print(THIN_SEP)
            print(f"  Sessions analyzed : {report.get('sessions_analyzed', 0)}")
            print(f"  Confidence trend  : {report.get('confidence_trend', 'N/A')}")
            print(f"  Collapse frequency: {report.get('collapse_frequency', 0)}")
            rec_count = report.get("recommendation_count", 0)
            print(f"  Recommendations   : {rec_count}")

        if cycle.introspection_summary:
            print()
            print(THIN_SEP)
            print("  Code Introspection")
            print(THIN_SEP)
            print(_wrap(cycle.introspection_summary))

        if cycle.proposals:
            print()
            print(THIN_SEP)
            print("  Optimization Proposals")
            print(THIN_SEP)
            for p in cycle.proposals[:5]:
                priority = p.get("priority", "?")
                title = p.get("title", "untitled")
                print(f"  [{priority.upper()}] {title}")

        if cycle.vir_report:
            vir = cycle.vir_report
            print()
            print(THIN_SEP)
            print("  MAGI_VIR Validation")
            print(THIN_SEP)
            print(f"  VIR ID         : {vir.get('vir_id', 'N/A')}")
            print(f"  Benchmarks     : {vir.get('benchmark_count', 0)}")
            print(f"  Improvement    : {vir.get('overall_improvement', 0):.4f}")
            print(f"  Recommendation : {vir.get('recommendation', 'N/A')}")
            print()
            print(_wrap(vir.get("summary", "")))

        if cycle.metadata.get("error"):
            print()
            print(f"  ERROR: {cycle.metadata['error']}")

    except Exception as e:
        print(f"\n[ERROR] Self-improvement cycle failed: {e}\n")

    print()
    print(SEPARATOR)
    print()


def _run_introspection():
    """Run analysis + introspection and display results."""
    from maestro.self_improve import SelfImprovementEngine

    print()
    print(SEPARATOR)
    print("  Code Introspection (Analysis Only)")
    print(SEPARATOR)
    print()

    try:
        engine = SelfImprovementEngine()
        result = engine.run_analysis_only()

        print(f"  Code targets found : {result.get('code_targets', 0)}")
        print(f"  Proposals generated: {result.get('proposal_count', 0)}")
        print()
        print(_wrap(result.get("introspection_summary", "No summary")))

        hotspots = result.get("complexity_hotspots", [])
        if hotspots:
            print()
            print(THIN_SEP)
            print("  Complexity Hotspots")
            print(THIN_SEP)
            for h in hotspots[:5]:
                print(f"  {h['function']:<30} {h['file']:<40} {h['complexity']:.2f}")

        proposals = result.get("proposals", [])
        if proposals:
            print()
            print(THIN_SEP)
            print("  Optimization Proposals")
            print(THIN_SEP)
            for p in proposals[:10]:
                priority = p.get("priority", "?")
                title = p.get("title", "untitled")
                category = p.get("category", "?")
                print(f"  [{priority.upper():<8}] [{category:<15}] {title}")

        summary = result.get("batch_summary", "")
        if summary:
            print()
            print(_wrap(summary))

    except Exception as e:
        print(f"\n[ERROR] Introspection failed: {e}\n")

    print()
    print(SEPARATOR)
    print()


def _show_improvement_cycles():
    """Show recent self-improvement cycles."""
    from maestro.self_improve import SelfImprovementEngine

    print()
    print(SEPARATOR)
    print("  Recent Improvement Cycles")
    print(SEPARATOR)
    print()

    try:
        engine = SelfImprovementEngine()
        cycles = engine.list_cycles(limit=10)

        if not cycles:
            print("  No improvement cycles recorded yet.")
            print("  Run /improve to start a self-improvement cycle.")
        else:
            print(f"  {'Timestamp':<22} {'Outcome':<14} {'Proposals':<10} {'Duration':<10} {'Node'}")
            print(f"  {'─' * 22} {'─' * 14} {'─' * 10} {'─' * 10} {'─' * 10}")
            for c in cycles:
                ts = c.get("timestamp", "?")[:19]
                outcome = c.get("outcome", "?")
                proposals = c.get("proposal_count", 0)
                duration = f"{c.get('duration_ms', 0)}ms"
                node = c.get("compute_node", "local")
                print(f"  {ts:<22} {outcome:<14} {proposals:<10} {duration:<10} {node}")

        total = engine.count_cycles()
        print(f"\n  Total cycles: {total}")

    except Exception as e:
        print(f"\n[ERROR] Failed to load cycles: {e}\n")

    print()
    print(SEPARATOR)
    print()


# ---------------------------------------------------------------------------
# Auto-update command
# ---------------------------------------------------------------------------

def _run_update():
    """Check for updates and optionally apply them."""
    from maestro.updater import check_for_updates, apply_update

    print()
    print(SEPARATOR)
    print("  Auto-Updater")
    print(SEPARATOR)
    print("  Checking for updates ...")
    print()

    try:
        info = check_for_updates()
    except Exception as e:
        print(f"  [ERROR] Update check failed: {e}")
        print()
        print(SEPARATOR)
        print()
        return

    if info.get("error"):
        print(f"  {info['error']}")
        print()
        print(SEPARATOR)
        print()
        return

    if not info["available"]:
        print(f"  Already up to date ({info['local_commit']} on {info['branch']}).")
        print()
        print(SEPARATOR)
        print()
        return

    commits = info.get("new_commits", [])
    print(f"  {len(commits)} new commit{'s' if len(commits) != 1 else ''} available on {info['branch']}:")
    print(f"  Local: {info['local_commit']}  ->  Remote: {info['remote_commit']}")
    print()
    for c in commits[:10]:
        print(f"    {c}")
    if len(commits) > 10:
        print(f"    ... and {len(commits) - 10} more")
    print()

    try:
        answer = input("  Apply update? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        answer = "n"

    if answer in ("n", "no"):
        print("  Update skipped.")
        print()
        print(SEPARATOR)
        print()
        return

    result = apply_update()
    print(f"  {result['message']}")

    if result["success"] and result["commits_pulled"] > 0:
        print()
        print("  Restart Maestro to use the new version:")
        print("    Docker : make up")
        print("    Local  : re-run python -m maestro.cli")

    print()
    print(SEPARATOR)
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

        if lower in ("/improve", "/self-improve"):
            _run_improvement_cycle()
            continue

        if lower in ("/introspect", "/inspect"):
            _run_introspection()
            continue

        if lower in ("/cycles", "/history"):
            _show_improvement_cycles()
            continue

        if lower in ("/update", "/upgrade"):
            _run_update()
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
