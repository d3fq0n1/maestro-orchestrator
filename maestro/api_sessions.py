"""
Session History API — REST endpoints for querying orchestration history.

Provides list and detail views over stored session records. Designed as
a FastAPI router that can be mounted by any backend entry point.

These endpoints are read-only. Sessions are written by the orchestrator
during normal operation — not by the API.

Error handling:
  - 404 when a session ID does not exist.
  - 422 when a stored session record is corrupted (malformed JSON).
  - 500 for unexpected storage errors.
"""

import json
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from maestro.session import SessionLogger


router = APIRouter(prefix="/api/sessions", tags=["sessions"])

_logger = SessionLogger()


@router.get("")
async def list_sessions(limit: int = 50, offset: int = 0):
    """List stored sessions, most recent first."""
    try:
        return {
            "sessions": _logger.list_sessions(limit=limit, offset=offset),
            "total": _logger.count(),
        }
    except Exception as e:
        print(f"[Sessions API Error] list_sessions: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list sessions: {str(e)}")


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Retrieve a full session record by ID."""
    try:
        record = _logger.load(session_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Session not found")
    except json.JSONDecodeError as e:
        print(f"[Sessions API Error] Malformed session file {session_id}: {e}")
        raise HTTPException(status_code=422, detail=f"Session record is corrupted: {str(e)}")
    except Exception as e:
        print(f"[Sessions API Error] load {session_id}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load session: {str(e)}")
    return asdict(record)
