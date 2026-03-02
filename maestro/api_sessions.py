"""
Session History API — REST endpoints for querying orchestration history.

Provides list and detail views over stored session records. Designed as
a FastAPI router that can be mounted by any backend entry point.

These endpoints are read-only. Sessions are written by the orchestrator
during normal operation — not by the API.
"""

from fastapi import APIRouter, HTTPException

from maestro.session import SessionLogger


router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_logger = SessionLogger()


@router.get("")
async def list_sessions(limit: int = 50, offset: int = 0):
    """List stored sessions, most recent first."""
    return {
        "sessions": _logger.list_sessions(limit=limit, offset=offset),
        "total": _logger.count(),
    }


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Retrieve a full session record by ID."""
    try:
        record = _logger.load(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    from dataclasses import asdict
    return asdict(record)
