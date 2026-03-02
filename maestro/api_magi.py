"""
MAGI API — REST endpoint for meta-agent governance analysis.

Provides on-demand MAGI analysis over the R2 ledger and session history.
This is the human-facing interface into the rapid recursion loop.
"""

from dataclasses import asdict

from fastapi import APIRouter

from maestro.magi import Magi


router = APIRouter(prefix="/api/magi", tags=["magi"])


@router.get("")
async def magi_analysis(ledger_limit: int = 50, session_limit: int = 50):
    """Run MAGI cross-session analysis and return recommendations."""
    magi = Magi()
    report = magi.analyze(
        ledger_limit=ledger_limit,
        session_limit=session_limit,
    )
    return {
        "sessions_analyzed": report.sessions_analyzed,
        "ledger_entries_analyzed": report.ledger_entries_analyzed,
        "confidence_trend": report.confidence_trend,
        "mean_confidence": report.mean_confidence,
        "grade_distribution": report.grade_distribution,
        "agent_health": report.agent_health,
        "collapse_frequency": report.collapse_frequency,
        "recurring_signals": report.recurring_signals,
        "recommendations": [asdict(r) for r in report.recommendations],
    }
