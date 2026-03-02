"""
MAGI: Meta-Agent Governance and Insight.

MAGI is the long-term memory of Maestro-Orchestrator. Where R2 scores a
single session and detects immediate problems, MAGI reads the R2 ledger
and session history to find patterns that span many sessions:

  - Which agents are consistently outliers?
  - Is confidence trending up or down?
  - Are certain prompt types triggering silent collapse repeatedly?
  - Is the system converging toward monoculture over time?

MAGI produces structured Recommendations — human-readable proposals for
system-level changes. It does NOT auto-apply changes (per the ethical
design principle: all interventions must be human-reviewable).

This is the "rapid recursion" loop:
  1. Observe  — Maestro runs sessions, R2 scores them
  2. Analyze  — MAGI reads the ledger and detects cross-session patterns
  3. Propose  — MAGI produces recommendations
  4. Apply    — A human (or future automation layer) acts on recommendations
"""

from dataclasses import dataclass, field
from collections import Counter

from maestro.r2 import R2Engine
from maestro.session import SessionLogger
from maestro.dissent import DissentAnalyzer


@dataclass
class Recommendation:
    """A structured proposal from MAGI for system-level change."""
    category: str       # "agent", "prompt", "system", "positive"
    severity: str       # "info", "warning", "critical"
    title: str          # short one-line summary
    description: str    # detailed explanation with evidence
    affected_agents: list = field(default_factory=list)
    evidence: dict = field(default_factory=dict)


@dataclass
class MagiReport:
    """Complete MAGI analysis across sessions."""
    sessions_analyzed: int
    ledger_entries_analyzed: int
    recommendations: list           # list of Recommendation
    confidence_trend: str           # "improving", "declining", "stable"
    mean_confidence: float
    grade_distribution: dict        # {"strong": N, "weak": N, ...}
    agent_health: dict              # {agent_name: {outlier_rate, sessions, ...}}
    collapse_frequency: float       # fraction of sessions with silent collapse
    recurring_signals: dict         # {signal_type: count}


class Magi:
    """
    Meta-agent governance layer. Reads R2 ledger and session history
    to detect cross-session patterns and produce recommendations.

    All analysis is read-only. MAGI never modifies the ledger, session
    records, or orchestrator configuration. It only observes and proposes.
    """

    def __init__(self, r2: R2Engine = None, session_logger: SessionLogger = None):
        self._r2 = r2 or R2Engine()
        self._sessions = session_logger or SessionLogger()

    def analyze(self, ledger_limit: int = 50, session_limit: int = 50) -> MagiReport:
        """
        Run full MAGI analysis across recent sessions and ledger entries.
        Returns a MagiReport with recommendations.
        """
        # --- Gather data ---
        trends = self._r2.analyze_ledger_trends(limit=ledger_limit)
        ledger_entries = self._r2._load_recent_entries(ledger_limit)
        session_summaries = self._sessions.list_sessions(limit=session_limit)

        # --- Cross-session agent health ---
        agent_health = self._analyze_agent_health(ledger_entries)

        # --- Collapse frequency ---
        collapse_count = sum(
            1 for e in ledger_entries
            if e.get("score", {}).get("silent_collapse", False)
        )
        total = len(ledger_entries)
        collapse_frequency = collapse_count / total if total > 0 else 0.0

        # --- Build recommendations ---
        recommendations = []
        recommendations.extend(self._agent_recommendations(agent_health, total))
        recommendations.extend(self._trend_recommendations(trends))
        recommendations.extend(self._collapse_recommendations(
            collapse_frequency, collapse_count, total,
        ))
        recommendations.extend(self._signal_recommendations(
            trends.get("recurring_signals", {}),
        ))
        recommendations.extend(self._positive_signals(trends, collapse_frequency))

        return MagiReport(
            sessions_analyzed=len(session_summaries),
            ledger_entries_analyzed=total,
            recommendations=recommendations,
            confidence_trend=self._classify_trend(trends),
            mean_confidence=trends.get("mean_confidence", 0.0),
            grade_distribution=trends.get("grade_distribution", {}),
            agent_health=agent_health,
            collapse_frequency=round(collapse_frequency, 4),
            recurring_signals=trends.get("recurring_signals", {}),
        )

    # --- Agent-level analysis ---

    def _analyze_agent_health(self, ledger_entries: list) -> dict:
        """
        Track per-agent health across sessions: how often each agent
        is an outlier, and what their average contribution looks like.
        """
        agent_stats: dict = {}  # {name: {outlier_count, total, ...}}

        for entry in ledger_entries:
            dissent = entry.get("dissent_summary", {})
            outliers = dissent.get("outlier_agents", [])
            agents = entry.get("agents_agreed", [])

            for name in agents:
                if name not in agent_stats:
                    agent_stats[name] = {"sessions": 0, "outlier_count": 0}
                agent_stats[name]["sessions"] += 1
                if name in outliers:
                    agent_stats[name]["outlier_count"] += 1

        # Compute outlier rates
        health = {}
        for name, stats in agent_stats.items():
            sessions = stats["sessions"]
            outlier_count = stats["outlier_count"]
            health[name] = {
                "sessions": sessions,
                "outlier_count": outlier_count,
                "outlier_rate": round(outlier_count / sessions, 4) if sessions > 0 else 0.0,
            }

        return health

    # --- Recommendation generators ---

    def _agent_recommendations(self, agent_health: dict, total_sessions: int) -> list:
        """Flag agents with high outlier rates."""
        recs = []
        for name, stats in agent_health.items():
            if stats["sessions"] < 3:
                continue  # not enough data
            if stats["outlier_rate"] > 0.5:
                recs.append(Recommendation(
                    category="agent",
                    severity="warning",
                    title=f"{name} is a persistent outlier",
                    description=(
                        f"{name} has been flagged as an outlier in "
                        f"{stats['outlier_count']} of {stats['sessions']} sessions "
                        f"({stats['outlier_rate']:.0%} outlier rate). "
                        f"Consider reviewing this agent's model configuration, "
                        f"temperature settings, or whether its divergence is "
                        f"providing valuable signal versus noise."
                    ),
                    affected_agents=[name],
                    evidence=stats,
                ))
        return recs

    def _trend_recommendations(self, trends: dict) -> list:
        """Flag concerning confidence trends."""
        recs = []
        trend_list = trends.get("trends", [])

        if "confidence_declining" in trend_list:
            recs.append(Recommendation(
                category="system",
                severity="warning",
                title="Confidence is declining across sessions",
                description=(
                    f"Mean confidence across recent sessions is "
                    f"{trends.get('mean_confidence', 0):.2%}. The trend shows "
                    f"declining quality. This may indicate model degradation, "
                    f"increasingly difficult prompts, or growing conformity "
                    f"pressure. Review recent session grades and R2 signals."
                ),
                evidence={
                    "mean_confidence": trends.get("mean_confidence"),
                    "grade_distribution": trends.get("grade_distribution"),
                },
            ))

        return recs

    def _collapse_recommendations(self, freq: float, count: int, total: int) -> list:
        """Flag frequent silent collapses."""
        recs = []
        if total >= 3 and freq > 0.3:
            recs.append(Recommendation(
                category="system",
                severity="critical",
                title="Frequent silent collapse detected",
                description=(
                    f"Silent collapse was detected in {count} of {total} "
                    f"recent sessions ({freq:.0%}). This suggests systematic "
                    f"RLHF conformity pressure is compressing the answer space. "
                    f"Consider: (1) diversifying the agent council with models "
                    f"from different providers, (2) adjusting temperature "
                    f"settings upward, (3) implementing prompt diversification "
                    f"to break consensus patterns."
                ),
                evidence={
                    "collapse_count": count,
                    "total_sessions": total,
                    "collapse_rate": round(freq, 4),
                },
            ))
        return recs

    def _signal_recommendations(self, recurring: dict) -> list:
        """Flag recurring R2 signals that indicate persistent problems."""
        recs = []
        for signal_type, count in recurring.items():
            if signal_type == "healthy_dissent":
                continue  # positive signal, handled elsewhere
            if count >= 3:
                recs.append(Recommendation(
                    category="system",
                    severity="warning",
                    title=f"Recurring signal: {signal_type}",
                    description=(
                        f"The R2 signal '{signal_type}' has appeared {count} "
                        f"times across recent sessions. This recurring pattern "
                        f"suggests a systemic issue that single-session fixes "
                        f"won't resolve. MAGI recommends reviewing the pattern "
                        f"and considering structural changes."
                    ),
                    evidence={"signal_type": signal_type, "count": count},
                ))
        return recs

    def _positive_signals(self, trends: dict, collapse_freq: float) -> list:
        """Detect positive health indicators."""
        recs = []
        trend_list = trends.get("trends", [])

        if "confidence_improving" in trend_list:
            recs.append(Recommendation(
                category="positive",
                severity="info",
                title="Confidence is improving",
                description=(
                    f"Mean confidence is {trends.get('mean_confidence', 0):.2%} "
                    f"and trending upward. The system is producing higher-quality "
                    f"consensus across sessions."
                ),
                evidence={"mean_confidence": trends.get("mean_confidence")},
            ))

        recurring = trends.get("recurring_signals", {})
        if recurring.get("healthy_dissent", 0) >= 2:
            recs.append(Recommendation(
                category="positive",
                severity="info",
                title="Healthy dissent is common",
                description=(
                    f"Healthy dissent has been observed in "
                    f"{recurring['healthy_dissent']} recent sessions. "
                    f"The council is maintaining diverse perspectives "
                    f"without individual agents dominating."
                ),
                evidence={"healthy_dissent_count": recurring["healthy_dissent"]},
            ))

        if collapse_freq == 0.0 and trends.get("entries_analyzed", 0) >= 5:
            recs.append(Recommendation(
                category="positive",
                severity="info",
                title="No silent collapse detected",
                description=(
                    f"Across {trends['entries_analyzed']} recent sessions, "
                    f"no silent collapse was detected. The NCG baseline is "
                    f"confirming that consensus reflects genuine reasoning "
                    f"rather than RLHF conformity."
                ),
            ))

        return recs

    def _classify_trend(self, trends: dict) -> str:
        """Classify the overall confidence trend."""
        trend_list = trends.get("trends", [])
        if "confidence_improving" in trend_list:
            return "improving"
        if "confidence_declining" in trend_list:
            return "declining"
        return "stable"
