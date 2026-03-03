"""
Self-Improvement API — REST endpoints for the rapid recursion pipeline.

Exposes the self-improvement engine through HTTP endpoints so the
Web-UI can trigger improvement cycles, inspect proposals, and
review validation results.  Also provides injection and rollback
endpoints for the code-injection system.
"""

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from maestro.self_improve import SelfImprovementEngine
from maestro.magi import Magi
from maestro.magi_vir import ComputeNodeRegistry, ComputeNode
from maestro.applicator import CodeInjector
from maestro.rollback import RollbackLog
from maestro.injection_guard import InjectionGuard


router = APIRouter(prefix="/api/self-improve", tags=["self-improve"])


@router.get("")
async def self_improve_status():
    """Get current self-improvement engine status and recent cycles."""
    engine = SelfImprovementEngine()
    cycles = engine.list_cycles(limit=10)
    return {
        "total_cycles": engine.count_cycles(),
        "recent_cycles": cycles,
    }


@router.post("/cycle")
async def run_improvement_cycle(compute_node: str = "local"):
    """
    Trigger a full self-improvement cycle.

    Runs: MAGI analysis → Code introspection → Proposal generation →
    MAGI_VIR validation → Promote/Reject
    """
    engine = SelfImprovementEngine(compute_node=compute_node)
    cycle = await asyncio.to_thread(engine.run_cycle)
    return asdict(cycle)


@router.post("/analyze")
async def run_analysis_only():
    """
    Run analysis + introspection without validation.
    Returns proposals and code targets for review.
    """
    engine = SelfImprovementEngine()
    return await asyncio.to_thread(engine.run_analysis_only)


@router.get("/cycle/{cycle_id}")
async def get_cycle(cycle_id: str):
    """Load a specific improvement cycle record."""
    engine = SelfImprovementEngine()
    cycle = engine.load_cycle(cycle_id)
    if cycle is None:
        raise HTTPException(status_code=404, detail="Cycle not found")
    return cycle


@router.get("/introspect")
async def introspect_with_magi():
    """
    Run MAGI analysis with code introspection.
    Returns standard MAGI report plus code optimization targets.
    """
    magi = Magi()
    result = await asyncio.to_thread(magi.analyze_with_introspection)
    report = result["report"]
    return {
        "sessions_analyzed": report.sessions_analyzed,
        "ledger_entries_analyzed": report.ledger_entries_analyzed,
        "confidence_trend": report.confidence_trend,
        "mean_confidence": report.mean_confidence,
        "recommendations": [asdict(r) for r in report.recommendations],
        "code_targets": result["code_targets"],
        "optimization_proposals": result["optimization_proposals"],
        "introspection_summary": result["introspection_summary"],
    }


@router.get("/nodes")
async def list_compute_nodes():
    """List available compute nodes for MAGI_VIR validation."""
    registry = ComputeNodeRegistry()
    nodes = registry.list_available()
    return {
        "nodes": [asdict(n) for n in nodes],
        "total": len(nodes),
    }


@router.post("/nodes")
async def register_compute_node(
    node_id: str,
    host: str,
    port: int = 8000,
):
    """Register a new compute node for distributed validation."""
    registry = ComputeNodeRegistry()
    node = ComputeNode(
        node_id=node_id,
        host=host,
        port=port,
        status="available",
        capabilities=["local_sandbox"],
    )
    registry.register(node)
    return asdict(node)


# ======================================================================
# Code Injection & Rollback endpoints
# ======================================================================

@router.post("/inject/{cycle_id}")
async def inject_cycle(cycle_id: str):
    """
    Manually inject proposals from a previously validated cycle.

    This is the human-in-the-loop path: review a cycle's proposals,
    then trigger injection via this endpoint.
    """
    engine = SelfImprovementEngine()
    result = await asyncio.to_thread(engine.inject_cycle, cycle_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/rollback/{rollback_id}")
async def rollback_injection(rollback_id: str):
    """Roll back a single injection by its rollback ID."""
    injector = CodeInjector()
    success = injector.rollback(rollback_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail="Rollback entry not found or already rolled back",
        )
    return {"rollback_id": rollback_id, "status": "rolled_back"}


@router.post("/rollback-cycle/{cycle_id}")
async def rollback_cycle(cycle_id: str):
    """Roll back all active injections from a given improvement cycle."""
    injector = CodeInjector()
    results = injector.rollback_cycle(cycle_id)
    if not results:
        raise HTTPException(
            status_code=404,
            detail="No active injections found for this cycle",
        )
    return {
        "cycle_id": cycle_id,
        "rollbacks": [
            {"rollback_id": rid, "success": ok} for rid, ok in results
        ],
    }


@router.get("/injections")
async def list_active_injections():
    """List all active (non-rolled-back) injections."""
    log = RollbackLog()
    active = log.get_active()
    return {
        "active_count": len(active),
        "injections": active,
    }


@router.get("/rollbacks")
async def list_rollback_history(limit: int = 50):
    """Full rollback history (newest first)."""
    log = RollbackLog()
    return {
        "total_active": log.count_active(),
        "history": log.list_all(limit=limit),
    }
