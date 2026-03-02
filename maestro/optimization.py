"""
Code Optimization Proposal System — Translates MAGI analysis into actionable changes.

The introspection engine identifies WHERE in Maestro's codebase optimizations
should happen. This module decides WHAT the optimization should be and
produces structured proposals that can be validated in a MAGI_VIR sandbox
before promotion.

Proposal categories:
  1. Threshold tuning — adjust numeric thresholds based on observed patterns
     (quorum threshold, similarity threshold, drift thresholds, etc.)
  2. Agent configuration — model versions, temperature, timeout adjustments
  3. Prompt optimization — restructure prompts for better token efficiency
  4. Pipeline reordering — adjust the sequence/parallelism of analysis steps
  5. Token-level tuning — adjust generation parameters based on logprob data

Each proposal is self-contained: it describes the current state, the proposed
state, the rationale, and the evidence from R2/MAGI that supports it. Proposals
are never auto-applied — they require validation through MAGI_VIR and human
approval (or future opt-in automation).
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from maestro.introspect import CodeTarget, IntrospectionReport


@dataclass
class OptimizationProposal:
    """A concrete, actionable proposal for improving Maestro's own code."""
    proposal_id: str
    timestamp: str
    category: str               # "threshold", "agent_config", "prompt", "pipeline",
                                # "token_tuning", "architecture"
    priority: str               # "low", "medium", "high", "critical"
    title: str                  # short description
    description: str            # detailed rationale with evidence

    # Target location
    file_path: str
    module_name: str
    target_name: str
    line_number: int

    # Change specification
    current_value: str          # what the code currently looks like
    proposed_value: str         # what it should change to
    change_type: str            # "parameter_update", "code_patch", "config_change",
                                # "prompt_rewrite", "architecture_refactor"

    # Evidence
    linked_signals: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)

    # Validation state
    status: str = "proposed"    # "proposed", "testing", "validated", "rejected",
                                # "promoted", "rolled_back"
    validation_result: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class ProposalBatch:
    """A collection of related proposals generated from a single analysis cycle."""
    batch_id: str
    timestamp: str
    proposals: list             # list of OptimizationProposal
    source_report: str          # "magi_analysis", "r2_signals", "token_analysis"
    summary: str
    total_proposals: int
    priority_breakdown: dict    # {"high": N, "medium": N, ...}


# --- Optimization strategy rules ---
# These encode the system's knowledge about how to respond to specific
# patterns detected by introspection. Each rule maps a signal type +
# optimization category to a specific change strategy.

_THRESHOLD_STRATEGIES = {
    "QUORUM_THRESHOLD": {
        "suspicious_consensus": {
            "direction": "raise",
            "step": 0.05,
            "min_val": 0.5,
            "max_val": 0.9,
            "rationale": "Raise quorum threshold to require stronger agreement, "
                         "reducing false consensus from RLHF conformity.",
        },
        "agent_degradation": {
            "direction": "lower",
            "step": 0.05,
            "min_val": 0.5,
            "max_val": 0.9,
            "rationale": "Lower quorum threshold to allow more sessions to reach "
                         "consensus when agents are degraded or topics are contested.",
        },
    },
    "SIMILARITY_THRESHOLD": {
        "persistent_outlier": {
            "direction": "raise",
            "step": 0.05,
            "min_val": 0.3,
            "max_val": 0.8,
            "rationale": "Raise similarity threshold to be less strict about what "
                         "counts as agreement, reducing false outlier detection.",
        },
        "suspicious_consensus": {
            "direction": "lower",
            "step": 0.05,
            "min_val": 0.3,
            "max_val": 0.8,
            "rationale": "Lower similarity threshold to require closer agreement "
                         "before counting agents as 'in consensus'.",
        },
    },
}

_TEMPERATURE_STRATEGIES = {
    "suspicious_consensus": {
        "direction": "raise",
        "step": 0.1,
        "min_val": 0.3,
        "max_val": 1.5,
        "rationale": "Raise agent temperature to increase output diversity and "
                     "break silent consensus patterns.",
    },
    "compression": {
        "direction": "raise",
        "step": 0.1,
        "min_val": 0.3,
        "max_val": 1.5,
        "rationale": "Raise temperature to produce more varied outputs and "
                     "counteract compression of nuance.",
    },
    "agent_degradation": {
        "direction": "lower",
        "step": 0.05,
        "min_val": 0.3,
        "max_val": 1.5,
        "rationale": "Lower temperature to produce more focused outputs when "
                     "agent quality is degrading.",
    },
}


class OptimizationEngine:
    """
    Generates optimization proposals from introspection results.

    Takes the code targets identified by the introspection engine
    and produces concrete, actionable proposals with specific
    parameter changes, code patches, or configuration updates.

    The engine encodes optimization strategies — rules that map
    observed patterns to specific changes. These strategies are
    themselves subject to MAGI's meta-analysis: if applied changes
    don't improve session quality, MAGI will detect the regression
    and propose rolling them back.
    """

    def generate_proposals(
        self,
        introspection_report: IntrospectionReport,
        magi_recommendations: list = None,
        r2_trends: dict = None,
    ) -> ProposalBatch:
        """
        Generate optimization proposals from introspection results.

        Args:
            introspection_report: output of CodeIntrospector.introspect()
            magi_recommendations: list of MAGI Recommendation objects
            r2_trends: dict from R2Engine.analyze_ledger_trends()

        Returns:
            ProposalBatch containing all generated proposals
        """
        r2_trends = r2_trends or {}
        proposals = []

        # Strategy 1: Threshold tuning from signal-mapped code targets
        proposals.extend(self._threshold_proposals(
            introspection_report.code_targets,
        ))

        # Strategy 2: Temperature/agent config adjustments
        proposals.extend(self._agent_config_proposals(
            introspection_report.code_targets,
        ))

        # Strategy 3: Token-level tuning proposals
        proposals.extend(self._token_tuning_proposals(
            introspection_report.token_level_targets,
        ))

        # Strategy 4: Architecture proposals from complexity hotspots
        proposals.extend(self._architecture_proposals(
            introspection_report.complexity_hotspots,
            magi_recommendations or [],
        ))

        # Strategy 5: Trend-driven priority escalation from R2 trends
        # If R2 detects declining confidence or recurring signals, escalate
        # matching proposals to higher priority.
        if r2_trends.get("trends") and "confidence_declining" in r2_trends["trends"]:
            for p in proposals:
                if p.priority == "medium":
                    p.priority = "high"
                    p.metadata["escalated_by"] = "confidence_declining_trend"

        # Deduplicate by (file_path, target_name, change_type)
        seen = set()
        unique = []
        for p in proposals:
            key = (p.file_path, p.target_name, p.change_type)
            if key not in seen:
                seen.add(key)
                unique.append(p)

        # Priority breakdown
        priority_counts = {}
        for p in unique:
            priority_counts[p.priority] = priority_counts.get(p.priority, 0) + 1

        summary_parts = [f"Generated {len(unique)} optimization proposal(s)."]
        if priority_counts.get("critical"):
            summary_parts.append(
                f"{priority_counts['critical']} critical priority."
            )
        if priority_counts.get("high"):
            summary_parts.append(
                f"{priority_counts['high']} high priority."
            )

        return ProposalBatch(
            batch_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            proposals=unique,
            source_report="magi_analysis",
            summary=" ".join(summary_parts),
            total_proposals=len(unique),
            priority_breakdown=priority_counts,
        )

    # --- Strategy implementations ---

    def _threshold_proposals(self, code_targets: list) -> list:
        """Generate threshold tuning proposals."""
        proposals = []

        for target in code_targets:
            if target.optimization_category != "threshold":
                continue

            strategies = _THRESHOLD_STRATEGIES.get(target.target_name, {})
            for signal_type in target.linked_signals:
                strategy = strategies.get(signal_type)
                if not strategy:
                    continue

                try:
                    current = float(target.current_value)
                except (ValueError, TypeError):
                    continue

                if strategy["direction"] == "raise":
                    proposed = min(current + strategy["step"], strategy["max_val"])
                else:
                    proposed = max(current - strategy["step"], strategy["min_val"])

                if proposed == current:
                    continue

                proposals.append(self._make_proposal(
                    category="threshold",
                    priority=self._signal_priority(signal_type),
                    title=f"Adjust {target.target_name}: {current} → {proposed}",
                    description=(
                        f"{strategy['rationale']} "
                        f"Triggered by recurring '{signal_type}' signals. "
                        f"Current value: {current}, proposed: {proposed}."
                    ),
                    target=target,
                    current_value=str(current),
                    proposed_value=str(proposed),
                    change_type="parameter_update",
                    linked_signals=[signal_type],
                ))

        return proposals

    def _agent_config_proposals(self, code_targets: list) -> list:
        """Generate agent configuration proposals (temperature, model, etc.)."""
        proposals = []

        for target in code_targets:
            if target.optimization_category != "agent_config":
                continue

            if target.target_name == "temperature":
                for signal_type in target.linked_signals:
                    strategy = _TEMPERATURE_STRATEGIES.get(signal_type)
                    if not strategy:
                        continue

                    # We propose temperature adjustment at the agent level
                    proposals.append(self._make_proposal(
                        category="agent_config",
                        priority=self._signal_priority(signal_type),
                        title=f"Adjust agent temperature ({strategy['direction']})",
                        description=(
                            f"{strategy['rationale']} "
                            f"Affected agents: "
                            f"{', '.join(target.metadata.get('affected_agents', ['all']))}."
                        ),
                        target=target,
                        current_value="current temperature",
                        proposed_value=f"temperature {strategy['direction']} by {strategy['step']}",
                        change_type="config_change",
                        linked_signals=[signal_type],
                    ))

            elif target.target_name in ("model", "timeout"):
                for signal_type in target.linked_signals:
                    if signal_type == "agent_degradation":
                        affected = target.metadata.get("affected_agents", [])
                        proposals.append(self._make_proposal(
                            category="agent_config",
                            priority="medium",
                            title=f"Review {target.target_name} for degraded agents",
                            description=(
                                f"Agent degradation detected. Consider updating "
                                f"{target.target_name} for agents: "
                                f"{', '.join(affected) if affected else 'all council members'}. "
                                f"Model versions may be stale or timeout too aggressive."
                            ),
                            target=target,
                            current_value=target.current_value,
                            proposed_value="requires manual review",
                            change_type="config_change",
                            linked_signals=[signal_type],
                        ))

        return proposals

    def _token_tuning_proposals(self, token_targets: list) -> list:
        """Generate proposals from token-level analysis."""
        proposals = []

        for target in token_targets:
            if target.optimization_category != "token_tuning":
                continue

            proposals.append(self._make_proposal(
                category="token_tuning",
                priority="medium",
                title=f"Token-level optimization: {target.target_name}",
                description=target.rationale,
                target=target,
                current_value=target.current_value,
                proposed_value="requires token-level analysis in MAGI_VIR",
                change_type="prompt_rewrite",
                linked_signals=target.linked_signals,
            ))

        return proposals

    def _architecture_proposals(self, complexity_hotspots: list,
                                magi_recommendations: list) -> list:
        """Generate architecture proposals from complexity hotspots + MAGI recs.

        Only generates proposals when MAGI has produced actionable
        recommendations — complexity alone is not enough to propose
        refactoring without evidence of a problem.
        """
        proposals = []

        # Only generate architecture proposals when MAGI has flagged issues
        actionable_recs = [
            r for r in magi_recommendations
            if hasattr(r, "severity") and r.severity in ("warning", "critical")
        ]
        if not actionable_recs:
            return proposals

        for hotspot in complexity_hotspots[:3]:  # top 3 most complex
            if hotspot["complexity"] > 0.6:
                proposals.append(OptimizationProposal(
                    proposal_id=str(uuid.uuid4()),
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    category="architecture",
                    priority="low",
                    title=f"Refactor complex function: {hotspot['function']}",
                    description=(
                        f"Function '{hotspot['function']}' in {hotspot['file']} "
                        f"has complexity score {hotspot['complexity']:.2f}. "
                        f"High complexity increases the risk of bugs and makes "
                        f"the rapid recursion loop harder to optimize. Consider "
                        f"decomposing into smaller, testable units."
                    ),
                    file_path=hotspot["file"],
                    module_name=hotspot["file"].replace("/", ".").replace(".py", ""),
                    target_name=hotspot["function"],
                    line_number=hotspot["line"],
                    current_value=f"complexity: {hotspot['complexity']:.2f}",
                    proposed_value="decomposed functions",
                    change_type="architecture_refactor",
                    linked_signals=["complexity_hotspot"],
                ))

        return proposals

    # --- Helpers ---

    def _make_proposal(
        self,
        category: str,
        priority: str,
        title: str,
        description: str,
        target: CodeTarget,
        current_value: str,
        proposed_value: str,
        change_type: str,
        linked_signals: list,
    ) -> OptimizationProposal:
        """Construct an OptimizationProposal from a CodeTarget."""
        return OptimizationProposal(
            proposal_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            category=category,
            priority=priority,
            title=title,
            description=description,
            file_path=target.file_path,
            module_name=target.module_name,
            target_name=target.target_name,
            line_number=target.line_number,
            current_value=current_value,
            proposed_value=proposed_value,
            change_type=change_type,
            linked_signals=linked_signals,
            evidence=target.metadata,
        )

    def _signal_priority(self, signal_type: str) -> str:
        """Map signal types to proposal priority levels."""
        priority_map = {
            "suspicious_consensus": "critical",
            "compression": "high",
            "persistent_outlier": "medium",
            "agent_degradation": "medium",
            "drift_trend": "medium",
            "healthy_dissent": "low",
            "token_uncertainty": "medium",
        }
        return priority_map.get(signal_type, "low")
