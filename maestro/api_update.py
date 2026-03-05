"""
API endpoints for the auto-updater.

GET  /api/update/check   — check if updates are available
POST /api/update/apply   — pull latest changes
"""

from fastapi import APIRouter
from maestro.updater import check_for_updates, apply_update

router = APIRouter(prefix="/api/update", tags=["update"])


@router.get("/check")
async def update_check():
    """Check the remote for new commits."""
    try:
        return check_for_updates()
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.post("/apply")
async def update_apply():
    """Pull latest changes from the remote."""
    try:
        return apply_update()
    except Exception as e:
        return {"success": False, "message": str(e), "commits_pulled": 0, "rebuilt": False}
