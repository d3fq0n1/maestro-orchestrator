"""
R2 Engine — Rapid Recursion & Reinforcement.

R2 is the system's reflex layer. After every orchestration session it
synthesizes signals from dissent analysis, NCG drift detection, and
quorum logic into a single session quality score, indexes the result
into a persistent ledger, and — critically — identifies improvement
signals that MAGI will eventually consume to propose code-level changes.

This is the prototype for self-improving software: Maestro nodes + NCG
run a session, dissent is measured, improvements are identified at the
meta-analysis layer, and R2 provides the structured signal that makes
rapid recursion possible.

Three responsibilities:
  1. Score — synthesize dissent, drift, and quorum into a quality grade
  2. Index — write consensus nodes to a persistent ledger with metadata
  3. Signal — detect patterns that indicate the system should change
     (persistent outliers, rising drift, compression trends, suspicious
     consensus) and produce structured improvement recommendations
"""

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from maestro.dissent import DissentReport
from maestro.ncg.drift import DriftReport


_DEFAULT_LEDGER_DIR = Path(__file__).resolve().parent.parent / "data" / "r2"


# --- Session scoring ---

@dataclass
class R2Score:
    """Quality assessment of a single orchestration session."""
    grade: str                  # "strong", "acceptable", "weak", "suspicious"
    confidence_score: float     # 0.0-1.0 composite quality
    quorum_met: bool
    internal_agreement: float   # from dissent analysis
    ncg_drift: float            # mean drift from headless baseline (0 if NCG disabled)
    silent_collapse: bool
    compression_alert: bool
    has_outliers: bool
    flags: list = field(default_factory=list)  # human-readable concern strings


@dataclass
class ImprovementSignal:
    """A structured observation that MAGI can consume to propose changes."""
    signal_type: str        # "persistent_outlier", "drift_trend", "compression",
                            # "suspicious_consensus", "agent_degradation"
    severity: str           # "info", "warning", "critical"
    description: str        # human-readable explanation
    affected_agents: list = field(default_factory=list)
    data: dict = field(default_factory=dict)  # supporting evidence


@dataclass
class R2LedgerEntry:
    """A single indexed consensus node in the R2 ledger."""
    entry_id: str
    timestamp: str
    session_id: str
    prompt: str
    consensus: str          # the merged/majority answer
    agents_agreed: list     # which agents participated
    score: R2Score
    improvement_signals: list   # list of ImprovementSignal
    ncg_attached: bool      # whether NCG drift data is present
    dissent_summary: dict   # condensed dissent metrics
    metadata: dict = field(default_factory=dict)


class R2Engine:
    """
    Scores sessions, indexes consensus nodes, and identifies improvement
    signals for the MAGI meta-analysis layer.

    The ledger accumulates over time. Each entry is a scored, indexed
    record of what the council produced and what the system observed
    about itself. MAGI reads this ledger to detect patterns that span
    sessions and propose code-level improvements — the rapid recursion
    loop.
    """

    def __init__(self, ledger_dir: str = None):
        self._dir = Path(ledger_dir) if ledger_dir else _DEFAULT_LEDGER_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    @property
    def ledger_dir(self) -> Path:
        return self._dir

    # --- Scoring ---

    def score_session(
        self,
        dissent_report: DissentReport,
        drift_report: DriftReport = None,
        quorum_confidence: str = "Low",
    ) -> R2Score:
        """
        Synthesize all analysis signals into a single session quality score.

        This is the reflex: look at what just happened and decide how
        good it was. The score feeds into the ledger and determines
        what improvement signals get raised.
        """
        flags = []

        # Extract NCG signals
        ncg_drift = 0.0
        silent_collapse = False
        compression_alert = False
        if drift_report is not None:
            ncg_drift = drift_report.mean_semantic_distance
            silent_collapse = drift_report.silent_collapse_detected
            compression_alert = drift_report.compression_alert

        # Extract dissent signals
        agreement = dissent_report.internal_agreement
        has_outliers = len(dissent_report.outlier_agents) > 0

        quorum_met = quorum_confidence in ("High", "Medium")

        # --- Flag generation ---
        if silent_collapse:
            flags.append("Silent collapse: agents agree but drift from headless baseline")

        if compression_alert:
            flags.append("Compression alert: conversational outputs significantly shorter than baseline")

        if has_outliers:
            names = ", ".join(dissent_report.outlier_agents)
            flags.append(f"Outlier agents detected: {names}")

        if agreement > 0.9 and ncg_drift > 0.5:
            flags.append("Suspicious consensus: very high agreement with high NCG drift")

        if dissent_report.dissent_level == "high":
            flags.append("High internal dissent: agents strongly disagree")

        if not quorum_met:
            flags.append("Quorum not met: insufficient agreement for consensus")

        # --- Grade assignment ---
        # Strong: quorum met, low drift, no collapse, no outliers
        # Acceptable: quorum met with some concerns
        # Weak: quorum not met or high dissent
        # Suspicious: silent collapse or suspicious consensus patterns
        if silent_collapse or (agreement > 0.9 and ncg_drift > 0.5):
            grade = "suspicious"
        elif not quorum_met or dissent_report.dissent_level == "high":
            grade = "weak"
        elif flags:
            grade = "acceptable"
        else:
            grade = "strong"

        # Composite confidence: weighted combination of signals
        # Higher is better. Penalize drift, reward agreement (unless suspicious).
        base = agreement * 0.4
        if drift_report is not None:
            base += (1.0 - ncg_drift) * 0.3
        else:
            base += 0.3  # no NCG data = no penalty
        base += (0.3 if quorum_met else 0.0)
        if silent_collapse:
            base *= 0.5  # halve score for silent collapse
        confidence_score = round(max(0.0, min(1.0, base)), 4)

        return R2Score(
            grade=grade,
            confidence_score=confidence_score,
            quorum_met=quorum_met,
            internal_agreement=agreement,
            ncg_drift=ncg_drift,
            silent_collapse=silent_collapse,
            compression_alert=compression_alert,
            has_outliers=has_outliers,
            flags=flags,
        )

    # --- Improvement signal detection ---

    def detect_signals(
        self,
        score: R2Score,
        dissent_report: DissentReport,
        drift_report: DriftReport = None,
    ) -> list:
        """
        Analyze the session score and reports to produce structured
        improvement signals. These are the observations MAGI will
        consume to propose system-level changes.
        """
        signals = []

        # Persistent outlier detection
        if score.has_outliers:
            signals.append(ImprovementSignal(
                signal_type="persistent_outlier",
                severity="warning",
                description=(
                    "One or more agents consistently diverge from the council. "
                    "MAGI should evaluate whether these agents need recalibration "
                    "or whether their dissent is providing valuable signal."
                ),
                affected_agents=dissent_report.outlier_agents,
                data={"agreement": score.internal_agreement},
            ))

        # Silent collapse — the most dangerous signal
        if score.silent_collapse:
            signals.append(ImprovementSignal(
                signal_type="suspicious_consensus",
                severity="critical",
                description=(
                    "All agents agree but their outputs have drifted from the "
                    "headless baseline. This may indicate RLHF conformity is "
                    "compressing the answer space. MAGI should consider prompt "
                    "diversification or agent rotation adjustments."
                ),
                affected_agents=[],
                data={
                    "ncg_drift": score.ncg_drift,
                    "internal_agreement": score.internal_agreement,
                },
            ))

        # Compression trend
        if score.compression_alert:
            signals.append(ImprovementSignal(
                signal_type="compression",
                severity="warning",
                description=(
                    "Conversational outputs are significantly shorter than the "
                    "headless baseline. Nuance is being lost. MAGI should consider "
                    "adjusting prompt length guidance or temperature settings."
                ),
                data={"ncg_drift": score.ncg_drift},
            ))

        # High dissent without outliers — healthy disagreement
        if dissent_report.dissent_level == "high" and not score.has_outliers:
            signals.append(ImprovementSignal(
                signal_type="healthy_dissent",
                severity="info",
                description=(
                    "Agents show high disagreement without clear outliers. "
                    "This may indicate a genuinely contested topic. R2 records "
                    "this as a positive diversity signal."
                ),
                data={"dissent_level": dissent_report.dissent_level},
            ))

        # Weak consensus
        if score.grade == "weak" and not score.quorum_met:
            signals.append(ImprovementSignal(
                signal_type="agent_degradation",
                severity="warning",
                description=(
                    "Quorum was not met. The council could not reach sufficient "
                    "agreement. MAGI should review agent configurations and "
                    "consider whether the prompt type exceeds current capabilities."
                ),
                data={"quorum_met": False, "confidence": score.confidence_score},
            ))

        return signals

    # --- Cross-session pattern detection ---

    def analyze_ledger_trends(self, limit: int = 20) -> dict:
        """
        Read recent ledger entries and detect patterns across sessions.
        Returns trend data that MAGI uses for longer-term improvements.
        """
        entries = self.load_recent_entries(limit)
        if len(entries) < 2:
            return {
                "entries_analyzed": len(entries),
                "trends": [],
                "mean_confidence": 0.0,
            }

        scores = [e.get("score", {}).get("confidence_score", 0.0) for e in entries]
        grades = [e.get("score", {}).get("grade", "unknown") for e in entries]

        mean_confidence = round(sum(scores) / len(scores), 4) if scores else 0.0

        # Detect grade distribution
        grade_counts = {}
        for g in grades:
            grade_counts[g] = grade_counts.get(g, 0) + 1

        # Detect confidence trend
        trends = []
        if len(scores) >= 4:
            mid = len(scores) // 2
            first_half = sum(scores[:mid]) / mid
            second_half = sum(scores[mid:]) / (len(scores) - mid)
            diff = second_half - first_half
            if diff > 0.1:
                trends.append("confidence_improving")
            elif diff < -0.1:
                trends.append("confidence_declining")

        # Count recurring signal types
        signal_counts = {}
        for e in entries:
            for sig in e.get("improvement_signals", []):
                st = sig.get("signal_type", "unknown")
                signal_counts[st] = signal_counts.get(st, 0) + 1

        recurring = {k: v for k, v in signal_counts.items() if v >= 2}
        if recurring:
            trends.append("recurring_signals")

        suspicious_count = grade_counts.get("suspicious", 0)
        if suspicious_count >= 2:
            trends.append("repeated_suspicious_consensus")

        return {
            "entries_analyzed": len(entries),
            "mean_confidence": mean_confidence,
            "grade_distribution": grade_counts,
            "recurring_signals": recurring,
            "trends": trends,
        }

    # --- Ledger persistence ---

    def index(
        self,
        session_id: str,
        prompt: str,
        consensus: str,
        agents_agreed: list,
        score: R2Score,
        improvement_signals: list,
        dissent_report: DissentReport,
        drift_report: DriftReport = None,
    ) -> R2LedgerEntry:
        """
        Write a scored consensus node to the R2 ledger.
        This is the durable record that accumulates over time.
        """
        entry = R2LedgerEntry(
            entry_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            session_id=session_id or "unknown",
            prompt=prompt,
            consensus=consensus,
            agents_agreed=agents_agreed,
            score=score,
            improvement_signals=improvement_signals,
            ncg_attached=drift_report is not None,
            dissent_summary={
                "internal_agreement": dissent_report.internal_agreement,
                "dissent_level": dissent_report.dissent_level,
                "outlier_agents": dissent_report.outlier_agents,
                "agent_count": dissent_report.agent_count,
            },
        )

        filepath = self._dir / f"{entry.entry_id}.json"
        data = asdict(entry)
        filepath.write_text(json.dumps(data, indent=2, default=str))
        return entry

    def load_entry(self, entry_id: str) -> dict:
        """Load a single ledger entry by ID."""
        filepath = self._dir / f"{entry_id}.json"
        return json.loads(filepath.read_text())

    def list_entries(self, limit: int = 50) -> list:
        """List ledger entries, most recent first (summaries only)."""
        files = sorted(self._dir.glob("*.json"), key=os.path.getmtime, reverse=True)
        summaries = []
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text())
                summaries.append({
                    "entry_id": data["entry_id"],
                    "timestamp": data["timestamp"],
                    "session_id": data["session_id"],
                    "prompt": data["prompt"][:120],
                    "grade": data.get("score", {}).get("grade", "unknown"),
                    "confidence": data.get("score", {}).get("confidence_score", 0.0),
                    "signal_count": len(data.get("improvement_signals", [])),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return summaries

    def count(self) -> int:
        """Total number of ledger entries."""
        return len(list(self._dir.glob("*.json")))

    def load_recent_entries(self, limit: int) -> list:
        """Load full entry data for recent entries."""
        files = sorted(self._dir.glob("*.json"), key=os.path.getmtime, reverse=True)
        entries = []
        for f in files[:limit]:
            try:
                entries.append(json.loads(f.read_text()))
            except json.JSONDecodeError:
                continue
        return entries
