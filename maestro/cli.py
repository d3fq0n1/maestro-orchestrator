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

# Load .env using the same logic as orchestrator_foundry.py.
# override=True ensures the volume-backed file wins over docker-compose env vars.
_dotenv_path = os.environ.get("MAESTRO_ENV_FILE") or os.path.join(_backend_dir, ".env")
load_dotenv(dotenv_path=_dotenv_path, override=True)

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
    print("    /nodes      — list storage nodes")
    print("    /plugins    — list loaded plugins")
    print("    /snapshot   — manage weight state snapshots")
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
# Storage node commands
# ---------------------------------------------------------------------------

def _show_nodes(args: str = ""):
    """List or manage storage nodes."""
    from maestro.shard_registry import StorageNodeRegistry, StorageNode

    parts = args.split() if args else []
    registry = StorageNodeRegistry()

    if not parts or parts[0] == "list":
        nodes = registry.list_nodes()
        print()
        print(SEPARATOR)
        print("  Storage Nodes")
        print(SEPARATOR)
        if not nodes:
            print("  No storage nodes registered.")
        else:
            print(f"  {'Node ID':<20} {'Host':<20} {'Status':<12} {'Shards':<8} {'Rep':<6}")
            print(f"  {'─' * 20} {'─' * 20} {'─' * 12} {'─' * 8} {'─' * 6}")
            for n in nodes:
                print(f"  {n.node_id:<20} {n.host}:{n.port:<13} {n.status:<12} "
                      f"{len(n.shards):<8} {n.reputation_score:.2f}")
        print()
        print(SEPARATOR)
        print()

    elif parts[0] == "register" and len(parts) >= 2:
        host_port = parts[1].split(":")
        host = host_port[0]
        port = int(host_port[1]) if len(host_port) > 1 else 8000
        import uuid
        node = StorageNode(
            node_id=f"node-{uuid.uuid4().hex[:8]}",
            host=host, port=port,
        )
        registry.register(node)
        print(f"  Registered node: {node.node_id} at {host}:{port}")

    elif parts[0] == "remove" and len(parts) >= 2:
        if registry.unregister(parts[1]):
            print(f"  Removed node: {parts[1]}")
        else:
            print(f"  Node not found: {parts[1]}")

    elif parts[0] == "health":
        nodes = registry.list_nodes()
        print()
        for n in nodes:
            print(f"  {n.node_id}: status={n.status}, rep={n.reputation_score:.2f}, "
                  f"latency={n.mean_latency_ms:.1f}ms")
        print()

    elif parts[0] == "pipeline" and len(parts) >= 2:
        pipeline = registry.build_inference_pipeline(parts[1])
        print()
        if not pipeline:
            print(f"  No pipeline available for model: {parts[1]}")
        else:
            print(f"  Inference pipeline for {parts[1]} ({len(pipeline)} hops):")
            for i, n in enumerate(pipeline):
                print(f"    {i + 1}. {n.node_id} ({n.host}:{n.port})")
        print()

    else:
        print("  Usage: /nodes [list|register <host:port>|remove <id>|health|pipeline <model>]")


# ---------------------------------------------------------------------------
# Plugin commands
# ---------------------------------------------------------------------------

def _show_plugins(args: str = ""):
    """List or manage plugins."""
    from maestro.plugins.manager import ModManager

    parts = args.split() if args else []
    manager = ModManager()
    manager.discover()

    if not parts or parts[0] == "list":
        plugins = manager.list_plugins()
        print()
        print(SEPARATOR)
        print("  Plugins")
        print(SEPARATOR)
        if not plugins:
            print("  No plugins discovered.")
        else:
            print(f"  {'Plugin ID':<30} {'Version':<10} {'Category':<12} {'State':<12}")
            print(f"  {'─' * 30} {'─' * 10} {'─' * 12} {'─' * 12}")
            for p in plugins:
                print(f"  {p['plugin_id']:<30} {p['version']:<10} "
                      f"{p['category']:<12} {p['state']:<12}")
        print()
        print(SEPARATOR)
        print()

    elif parts[0] == "enable" and len(parts) >= 2:
        if manager.load(parts[1]) and manager.enable(parts[1]):
            print(f"  Enabled plugin: {parts[1]}")
        else:
            print(f"  Failed to enable plugin: {parts[1]}")

    elif parts[0] == "disable" and len(parts) >= 2:
        if manager.disable(parts[1]):
            print(f"  Disabled plugin: {parts[1]}")
        else:
            print(f"  Failed to disable plugin: {parts[1]}")

    elif parts[0] == "reload" and len(parts) >= 2:
        if manager.reload(parts[1]):
            print(f"  Reloaded plugin: {parts[1]}")
        else:
            print(f"  Failed to reload plugin: {parts[1]}")

    elif parts[0] == "health":
        health = manager.health_check_all()
        print()
        for pid, status in health.items():
            healthy = "OK" if status.get("healthy") else "FAIL"
            msg = status.get("message", "")
            print(f"  {pid}: [{healthy}] {msg}")
        if not health:
            print("  No enabled plugins to check.")
        print()

    elif parts[0] == "info" and len(parts) >= 2:
        info = manager.get_plugin_info(parts[1])
        if info:
            print()
            for k, v in info.items():
                print(f"  {k}: {v}")
            print()
        else:
            print(f"  Plugin not found: {parts[1]}")

    else:
        print("  Usage: /plugins [list|enable <id>|disable <id>|reload <id>|health|info <id>]")


# ---------------------------------------------------------------------------
# Snapshot commands
# ---------------------------------------------------------------------------

def _manage_snapshots(args: str = ""):
    """Manage weight state snapshots."""
    from maestro.plugins.manager import ModManager

    parts = args.split() if args else []
    manager = ModManager()

    if not parts or parts[0] == "list":
        snapshots = manager.list_snapshots()
        print()
        print(SEPARATOR)
        print("  Weight State Snapshots")
        print(SEPARATOR)
        if not snapshots:
            print("  No snapshots saved.")
        else:
            for s in snapshots:
                print(f"  {s['name']:<20} {s['created_at'][:19]:<22} "
                      f"plugins: {s['enabled_plugins']}")
                if s.get("description"):
                    print(f"    {s['description']}")
        print()
        print(SEPARATOR)
        print()

    elif parts[0] == "save" and len(parts) >= 2:
        name = parts[1]
        desc = " ".join(parts[2:]) if len(parts) > 2 else ""
        snap = manager.save_snapshot(name, desc)
        print(f"  Snapshot saved: {snap.snapshot_id} ({snap.name})")

    elif parts[0] == "restore" and len(parts) >= 2:
        # Look up by name or ID
        snapshots = manager.list_snapshots()
        target = None
        for s in snapshots:
            if s["name"] == parts[1] or s["snapshot_id"] == parts[1]:
                target = s["snapshot_id"]
                break
        if target:
            if manager.restore_snapshot(target):
                print(f"  Snapshot restored: {parts[1]}")
            else:
                print(f"  Failed to restore snapshot: {parts[1]}")
        else:
            print(f"  Snapshot not found: {parts[1]}")

    elif parts[0] == "diff" and len(parts) >= 3:
        diff = manager.diff_snapshots(parts[1], parts[2])
        print()
        if "error" in diff:
            print(f"  {diff['error']}")
        else:
            print(f"  Comparing: {diff['snapshot_a']['name']} vs {diff['snapshot_b']['name']}")
            if diff.get("plugins_added"):
                print(f"  Added: {', '.join(diff['plugins_added'])}")
            if diff.get("plugins_removed"):
                print(f"  Removed: {', '.join(diff['plugins_removed'])}")
            if diff.get("config_changes"):
                print(f"  Config changes: {len(diff['config_changes'])} plugin(s)")
        print()

    else:
        print("  Usage: /snapshot [list|save <name> [desc]|restore <name>|diff <a> <b>]")


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

        if lower.startswith("/nodes"):
            _show_nodes(user_input[6:].strip())
            continue

        if lower.startswith("/plugins"):
            _show_plugins(user_input[8:].strip())
            continue

        if lower.startswith("/snapshot"):
            _manage_snapshots(user_input[9:].strip())
            continue

        if lower.startswith("/challenge"):
            args = user_input[10:].strip()
            if args:
                from maestro.storage_proof import StorageProofEngine
                engine = StorageProofEngine()
                challenge = engine.issue_challenge(args, "probe", "latency_probe")
                print(f"  Challenge issued: {challenge.challenge_id} -> {args}")
            else:
                print("  Usage: /challenge <node_id>")
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
