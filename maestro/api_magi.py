"""
MAGI API — REST endpoint for meta-agent governance analysis.

Provides on-demand MAGI analysis over the R2 ledger and session history.
This is the human-facing interface into the rapid recursion loop.

Error handling:
  - 500 with descriptive detail if MAGI analysis raises unexpectedly.
  - Empty ledger / no sessions returns a valid report with zero counts,
    not an error — that is normal on a fresh install.
"""

from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from maestro.magi import Magi


router = APIRouter(prefix="/api/magi", tags=["magi"])


@router.get("")
async def magi_analysis(ledger_limit: int = 50, session_limit: int = 50):
    """Run MAGI cross-session analysis and return recommendations."""
    try:
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
    except Exception as e:
        print(f"[MAGI API Error] {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"MAGI analysis failed: {str(e)}",
        )
