"""
Code Introspection Engine — MAGI's eye into Maestro's own source code.

This module gives MAGI the ability to analyze Maestro-Orchestrator's own
codebase and runtime behavior to identify optimization opportunities. It
bridges the gap between R2's improvement signals (which describe *what* is
wrong at the session/pattern level) and actual *code-level changes* that
could fix those patterns.

Three analysis tiers:
  1. Source analysis — static inspection of maestro source files, AST
     parsing, complexity metrics, identification of hot paths
  2. Runtime signal mapping — maps R2 ImprovementSignals and MAGI
     Recommendations to specific code locations and parameters
  3. Token-level behavior analysis — when logprob data is available,
     identifies where prompt construction or agent configuration is
     causing suboptimal token distributions

The introspection engine is read-only with respect to the running system.
It produces CodeTarget objects that the optimization proposal system
consumes to generate actual change proposals.
"""

import ast
import os
import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_MAESTRO_ROOT = Path(__file__).resolve().parent


@dataclass
class CodeTarget:
    """A specific location in Maestro's source that may benefit from optimization."""
    file_path: str              # relative to maestro package root
    module_name: str            # e.g. "maestro.orchestrator"
    target_type: str            # "function", "class", "parameter", "config", "prompt_template"
    target_name: str            # e.g. "score_session", "QUORUM_THRESHOLD"
    line_number: int
    current_value: str          # current code/value at this location
    optimization_category: str  # "prompt", "pipeline", "agent_config", "token_tuning",
                                # "threshold", "architecture"
    rationale: str              # why this target was identified
    linked_signals: list = field(default_factory=list)  # R2 signal_types that pointed here
    complexity_score: float = 0.0  # 0-1, higher = more complex = more opportunity
    metadata: dict = field(default_factory=dict)


@dataclass
class IntrospectionReport:
    """Complete analysis of Maestro's codebase for optimization opportunities."""
    files_analyzed: int
    total_functions: int
    total_classes: int
    code_targets: list          # list of CodeTarget
    complexity_hotspots: list   # files/functions ranked by complexity
    signal_mappings: dict       # {signal_type: [CodeTarget, ...]}
    token_level_targets: list   # targets identified from logprob analysis
    summary: str


# --- Signal-to-code mapping rules ---
# These rules map R2 improvement signal types to the code locations
# most likely responsible. This is the core of MAGI's self-awareness.

_SIGNAL_CODE_MAP = {
    "persistent_outlier": [
        {"module": "maestro.agents", "targets": ["temperature", "model", "timeout"],
         "category": "agent_config",
         "rationale": "Persistent outlier agents may need temperature, model, or timeout adjustments"},
        {"module": "maestro.dissent", "targets": ["_semantic_distance", "threshold"],
         "category": "threshold",
         "rationale": "Outlier detection threshold may be too sensitive or too lenient"},
    ],
    "suspicious_consensus": [
        {"module": "maestro.orchestrator", "targets": ["run_orchestration_async"],
         "category": "pipeline",
         "rationale": "Silent collapse in the pipeline may require prompt diversification"},
        {"module": "maestro.ncg.drift", "targets": ["_semantic_distance", "silent_collapse"],
         "category": "threshold",
         "rationale": "Silent collapse detection thresholds may need recalibration"},
        {"module": "maestro.aggregator", "targets": ["QUORUM_THRESHOLD", "SIMILARITY_THRESHOLD"],
         "category": "threshold",
         "rationale": "Quorum thresholds may be allowing false consensus through"},
    ],
    "compression": [
        {"module": "maestro.ncg.generator", "targets": ["generate", "temperature"],
         "category": "prompt",
         "rationale": "Compression may be caused by prompt construction or temperature settings"},
        {"module": "maestro.agents", "targets": ["max_tokens", "temperature"],
         "category": "agent_config",
         "rationale": "Agent output length limits or temperature may be compressing nuance"},
    ],
    "agent_degradation": [
        {"module": "maestro.agents", "targets": ["model", "timeout", "fetch"],
         "category": "agent_config",
         "rationale": "Agent degradation may indicate model version staleness or timeout issues"},
        {"module": "maestro.orchestrator", "targets": ["run_orchestration_async"],
         "category": "pipeline",
         "rationale": "Pipeline structure may need rebalancing after degradation"},
    ],
    "drift_trend": [
        {"module": "maestro.ncg.drift", "targets": ["DriftDetector", "analyze"],
         "category": "architecture",
         "rationale": "Rising drift trend may indicate the drift detector needs recalibration"},
        {"module": "maestro.ncg.generator", "targets": ["temperature"],
         "category": "token_tuning",
         "rationale": "Headless generator temperature may need adjustment to track drift"},
    ],
}


class CodeIntrospector:
    """
    Analyzes Maestro's own source code to identify optimization targets.

    Operates in three tiers:
      1. Static source analysis — AST parsing, complexity scoring
      2. Signal-to-code mapping — links R2 signals to code locations
      3. Token-level target identification — logprob-driven analysis
    """

    def __init__(self, source_root: Path = None):
        self._root = source_root or _MAESTRO_ROOT
        self._source_cache: dict = {}

    # --- Tier 1: Static source analysis ---

    def _discover_source_files(self) -> list:
        """Find all Python source files in the maestro package."""
        files = []
        for path in self._root.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            files.append(path)
        return sorted(files)

    def _parse_file(self, filepath: Path) -> Optional[ast.Module]:
        """Parse a Python source file into an AST, caching the result."""
        key = str(filepath)
        if key in self._source_cache:
            return self._source_cache[key]
        try:
            source = filepath.read_text()
            tree = ast.parse(source, filename=str(filepath))
            self._source_cache[key] = tree
            return tree
        except (SyntaxError, UnicodeDecodeError):
            return None

    def _compute_complexity(self, node: ast.AST) -> float:
        """
        Compute a simple cyclomatic complexity proxy for a function/class.
        Counts branching statements, loops, exception handlers, and
        boolean operators. Normalizes to 0-1 range.
        """
        branch_count = 0
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.IfExp)):
                branch_count += 1
            elif isinstance(child, (ast.For, ast.While, ast.AsyncFor)):
                branch_count += 1
            elif isinstance(child, ast.ExceptHandler):
                branch_count += 1
            elif isinstance(child, ast.BoolOp):
                branch_count += len(child.values) - 1
            elif isinstance(child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                branch_count += 1
        # Normalize: complexity of 10+ branches = 1.0
        return min(1.0, branch_count / 10.0)

    def analyze_source(self) -> dict:
        """
        Perform static analysis of all maestro source files.
        Returns file-level and function-level complexity metrics.
        """
        files = self._discover_source_files()
        results = {
            "files": [],
            "total_functions": 0,
            "total_classes": 0,
            "complexity_hotspots": [],
        }

        for filepath in files:
            tree = self._parse_file(filepath)
            if tree is None:
                continue

            rel_path = str(filepath.relative_to(self._root.parent))
            functions = []
            classes = []

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    complexity = self._compute_complexity(node)
                    functions.append({
                        "name": node.name,
                        "line": node.lineno,
                        "complexity": round(complexity, 4),
                    })
                    results["total_functions"] += 1

                    if complexity > 0.3:
                        results["complexity_hotspots"].append({
                            "file": rel_path,
                            "function": node.name,
                            "line": node.lineno,
                            "complexity": round(complexity, 4),
                        })

                elif isinstance(node, ast.ClassDef):
                    classes.append({
                        "name": node.name,
                        "line": node.lineno,
                    })
                    results["total_classes"] += 1

            results["files"].append({
                "path": rel_path,
                "functions": functions,
                "classes": classes,
            })

        results["complexity_hotspots"].sort(
            key=lambda x: x["complexity"], reverse=True,
        )
        return results

    # --- Tier 2: Signal-to-code mapping ---

    def map_signals_to_code(self, improvement_signals: list) -> dict:
        """
        Map R2 improvement signals to specific code targets.

        Takes a list of ImprovementSignal objects (or dicts with
        signal_type keys) and returns a mapping of signal types to
        CodeTarget objects identifying where in the source code the
        optimization should happen.
        """
        mappings = {}

        for signal in improvement_signals:
            if hasattr(signal, "signal_type"):
                sig_type = signal.signal_type
                affected = getattr(signal, "affected_agents", [])
                sig_data = getattr(signal, "data", {})
            else:
                sig_type = signal.get("signal_type", "unknown")
                affected = signal.get("affected_agents", [])
                sig_data = signal.get("data", {})

            rules = _SIGNAL_CODE_MAP.get(sig_type, [])
            targets = []

            for rule in rules:
                module_name = rule["module"]
                # Resolve module to file path
                module_path = self._resolve_module_path(module_name)
                if module_path is None:
                    continue

                tree = self._parse_file(module_path)
                if tree is None:
                    continue

                rel_path = str(module_path.relative_to(self._root.parent))

                for target_name in rule["targets"]:
                    location = self._find_in_ast(tree, target_name)
                    if location:
                        targets.append(CodeTarget(
                            file_path=rel_path,
                            module_name=module_name,
                            target_type=location["type"],
                            target_name=target_name,
                            line_number=location["line"],
                            current_value=location.get("value", ""),
                            optimization_category=rule["category"],
                            rationale=rule["rationale"],
                            linked_signals=[sig_type],
                            complexity_score=location.get("complexity", 0.0),
                            metadata={
                                "affected_agents": affected,
                                "signal_data": sig_data,
                            },
                        ))

            if targets:
                mappings[sig_type] = targets

        return mappings

    def _resolve_module_path(self, module_name: str) -> Optional[Path]:
        """Resolve a dotted module name to a file path."""
        parts = module_name.split(".")
        if parts[0] == "maestro":
            parts = parts[1:]

        # Try as a file first
        candidate = self._root / "/".join(parts)
        if candidate.with_suffix(".py").exists():
            return candidate.with_suffix(".py")

        # Try as a package directory (look at all files in it)
        if candidate.is_dir():
            init = candidate / "__init__.py"
            if init.exists():
                return init

        return None

    def _find_in_ast(self, tree: ast.Module, name: str) -> Optional[dict]:
        """
        Find a named entity (function, class, variable) in an AST.
        Returns location info dict or None.
        """
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == name:
                    return {
                        "type": "function",
                        "line": node.lineno,
                        "complexity": self._compute_complexity(node),
                    }
            elif isinstance(node, ast.ClassDef):
                if node.name == name:
                    return {
                        "type": "class",
                        "line": node.lineno,
                        "complexity": self._compute_complexity(node),
                    }
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        try:
                            value = ast.literal_eval(node.value)
                            value_str = repr(value)
                        except (ValueError, TypeError):
                            value_str = ast.dump(node.value)
                        return {
                            "type": "parameter",
                            "line": node.lineno,
                            "value": value_str,
                        }
        return None

    # --- Tier 3: Token-level target identification ---

    def analyze_token_patterns(self, ledger_entries: list) -> list:
        """
        Analyze token-level data from R2 ledger entries to identify
        optimization targets at the prompt/generation level.

        This is where conversational metadata analysis bridges to
        pure token-level behavior. When logprob data is available,
        we can identify:
          - Prompts that consistently produce high-uncertainty tokens
          - Token positions where the model is most contested
          - Patterns in contested tokens that suggest prompt rewording

        Returns list of CodeTarget objects for token-level optimizations.
        """
        targets = []
        token_patterns = {
            "high_uncertainty_prompts": [],
            "contested_positions": [],
            "compression_signatures": [],
        }

        for entry in ledger_entries:
            signals = entry.get("improvement_signals", [])
            score = entry.get("score", {})
            dissent = entry.get("dissent_summary", {})

            # Look for entries with token-level drift data
            for signal in signals:
                token_drift = signal.get("data", {}).get("token_drift", {})
                if not token_drift:
                    continue

                uncertain_count = token_drift.get("uncertain_token_count", 0)
                contested_count = token_drift.get("contested_token_count", 0)
                total_tokens = token_drift.get("total_tokens", 1)

                # High uncertainty ratio suggests prompt needs restructuring
                if total_tokens > 0 and uncertain_count / total_tokens > 0.2:
                    token_patterns["high_uncertainty_prompts"].append({
                        "prompt": entry.get("prompt", "")[:200],
                        "uncertainty_ratio": uncertain_count / total_tokens,
                        "entry_id": entry.get("entry_id"),
                    })

                # Contested tokens suggest the model was torn between outputs
                if contested_count > 3:
                    token_patterns["contested_positions"].append({
                        "contested_tokens": token_drift.get("contested_tokens", []),
                        "entry_id": entry.get("entry_id"),
                    })

            # Compression signature: high agreement but low confidence
            if (score.get("compression_alert") and
                    dissent.get("internal_agreement", 0) > 0.8):
                token_patterns["compression_signatures"].append({
                    "prompt": entry.get("prompt", "")[:200],
                    "entry_id": entry.get("entry_id"),
                })

        # Generate code targets from token patterns
        if token_patterns["high_uncertainty_prompts"]:
            targets.append(CodeTarget(
                file_path="maestro/ncg/generator.py",
                module_name="maestro.ncg.generator",
                target_type="parameter",
                target_name="temperature",
                line_number=0,
                current_value="1.0",
                optimization_category="token_tuning",
                rationale=(
                    f"High token uncertainty detected in "
                    f"{len(token_patterns['high_uncertainty_prompts'])} sessions. "
                    f"Temperature or prompt structure may need adjustment to reduce "
                    f"uncertainty at decision-critical token positions."
                ),
                linked_signals=["token_uncertainty"],
                metadata={"patterns": token_patterns["high_uncertainty_prompts"][:5]},
            ))

        if token_patterns["compression_signatures"]:
            targets.append(CodeTarget(
                file_path="maestro/orchestrator.py",
                module_name="maestro.orchestrator",
                target_type="function",
                target_name="run_orchestration_async",
                line_number=0,
                current_value="",
                optimization_category="token_tuning",
                rationale=(
                    f"Compression signatures detected in "
                    f"{len(token_patterns['compression_signatures'])} sessions. "
                    f"Agents are producing shorter outputs while agreeing, suggesting "
                    f"RLHF pressure is compressing at the token level."
                ),
                linked_signals=["compression"],
                metadata={"patterns": token_patterns["compression_signatures"][:5]},
            ))

        return targets

    # --- Full introspection report ---

    def introspect(self, improvement_signals: list = None,
                   ledger_entries: list = None) -> IntrospectionReport:
        """
        Run full introspection: static analysis + signal mapping + token analysis.

        Args:
            improvement_signals: list of R2 ImprovementSignal objects or dicts
            ledger_entries: list of R2 ledger entry dicts for token analysis

        Returns:
            IntrospectionReport with all identified optimization targets
        """
        # Tier 1: Static analysis
        source_analysis = self.analyze_source()

        # Tier 2: Signal-to-code mapping
        signal_mappings = {}
        if improvement_signals:
            signal_mappings = self.map_signals_to_code(improvement_signals)

        # Tier 3: Token-level targets
        token_targets = []
        if ledger_entries:
            token_targets = self.analyze_token_patterns(ledger_entries)

        # Collect all code targets
        all_targets = []
        for targets in signal_mappings.values():
            all_targets.extend(targets)
        all_targets.extend(token_targets)

        # Deduplicate by (file_path, target_name)
        seen = set()
        unique_targets = []
        for t in all_targets:
            key = (t.file_path, t.target_name)
            if key not in seen:
                seen.add(key)
                unique_targets.append(t)

        summary_parts = [
            f"Analyzed {source_analysis['total_functions']} functions "
            f"across {len(source_analysis['files'])} files.",
        ]
        if unique_targets:
            summary_parts.append(
                f"Identified {len(unique_targets)} optimization target(s) "
                f"from {len(signal_mappings)} signal type(s)."
            )
        if token_targets:
            summary_parts.append(
                f"{len(token_targets)} target(s) from token-level analysis."
            )
        if source_analysis["complexity_hotspots"]:
            top = source_analysis["complexity_hotspots"][0]
            summary_parts.append(
                f"Highest complexity: {top['function']} in {top['file']} "
                f"(score: {top['complexity']})."
            )

        return IntrospectionReport(
            files_analyzed=len(source_analysis["files"]),
            total_functions=source_analysis["total_functions"],
            total_classes=source_analysis["total_classes"],
            code_targets=unique_targets,
            complexity_hotspots=source_analysis["complexity_hotspots"],
            signal_mappings=signal_mappings,
            token_level_targets=token_targets,
            summary=" ".join(summary_parts),
        )
