"""
Self-Improvement API — REST endpoints for the rapid recursion pipeline.

Exposes the self-improvement engine through HTTP endpoints so the
Web-UI can trigger improvement cycles, inspect proposals, and
review validation results.  Also provides injection and rollback
endpoints for the code-injection system.

Error handling:
  - 404 for missing cycles, nodes, or rollback entries.
  - 400 when an operation is rejected due to state (e.g. injecting a
    non-promoted cycle).
  - 500 with descriptive detail for unexpected internal failures.
  - All long-running operations run in a thread pool via asyncio.to_thread
    to avoid blocking the event loop.
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
    try:
        engine = SelfImprovementEngine()
        cycles = engine.list_cycles(limit=10)
        return {
            "total_cycles": engine.count_cycles(),
            "recent_cycles": cycles,
        }
    except Exception as e:
        print(f"[SelfImprove API Error] status: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve status: {str(e)}")


@router.post("/cycle")
async def run_improvement_cycle(compute_node: str = "local"):
    """
    Trigger a full self-improvement cycle.

    Runs: MAGI analysis → Code introspection → Proposal generation →
    MAGI_VIR validation → Promote/Reject
    """
    try:
        engine = SelfImprovementEngine(compute_node=compute_node)
        cycle = await asyncio.to_thread(engine.run_cycle)
        return asdict(cycle)
    except Exception as e:
        print(f"[SelfImprove API Error] run_cycle: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Improvement cycle failed: {str(e)}")


@router.post("/analyze")
async def run_analysis_only():
    """
    Run analysis + introspection without validation.
    Returns proposals and code targets for review.
    """
    try:
        engine = SelfImprovementEngine()
        return await asyncio.to_thread(engine.run_analysis_only)
    except Exception as e:
        print(f"[SelfImprove API Error] analyze: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@router.get("/cycle/{cycle_id}")
async def get_cycle(cycle_id: str):
    """Load a specific improvement cycle record."""
    try:
        engine = SelfImprovementEngine()
        cycle = engine.load_cycle(cycle_id)
        if cycle is None:
            raise HTTPException(status_code=404, detail="Cycle not found")
        return cycle
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SelfImprove API Error] get_cycle {cycle_id}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to load cycle: {str(e)}")


@router.get("/introspect")
async def introspect_with_magi():
    """
    Run MAGI analysis with code introspection.
    Returns standard MAGI report plus code optimization targets.
    """
    try:
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
    except Exception as e:
        print(f"[SelfImprove API Error] introspect: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Introspection failed: {str(e)}")


@router.get("/nodes")
async def list_compute_nodes():
    """List available compute nodes for MAGI_VIR validation."""
    try:
        registry = ComputeNodeRegistry()
        nodes = registry.list_available()
        return {
            "nodes": [asdict(n) for n in nodes],
            "total": len(nodes),
        }
    except Exception as e:
        print(f"[SelfImprove API Error] list_nodes: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list nodes: {str(e)}")


@router.post("/nodes")
async def register_compute_node(
    node_id: str,
    host: str,
    port: int = 8000,
):
    """Register a new compute node for distributed validation."""
    try:
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
    except Exception as e:
        print(f"[SelfImprove API Error] register_node: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to register node: {str(e)}")


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
    try:
        engine = SelfImprovementEngine()
        result = await asyncio.to_thread(engine.inject_cycle, cycle_id)
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        return result
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SelfImprove API Error] inject_cycle {cycle_id}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Injection failed: {str(e)}")


@router.post("/rollback/{rollback_id}")
async def rollback_injection(rollback_id: str):
    """Roll back a single injection by its rollback ID."""
    try:
        injector = CodeInjector()
        success = injector.rollback(rollback_id)
        if not success:
            raise HTTPException(
                status_code=404,
                detail="Rollback entry not found or already rolled back",
            )
        return {"rollback_id": rollback_id, "status": "rolled_back"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SelfImprove API Error] rollback {rollback_id}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Rollback failed: {str(e)}")


@router.post("/rollback-cycle/{cycle_id}")
async def rollback_cycle(cycle_id: str):
    """Roll back all active injections from a given improvement cycle."""
    try:
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
    except HTTPException:
        raise
    except Exception as e:
        print(f"[SelfImprove API Error] rollback_cycle {cycle_id}: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Cycle rollback failed: {str(e)}")


@router.get("/injections")
async def list_active_injections():
    """List all active (non-rolled-back) injections."""
    try:
        log = RollbackLog()
        active = log.get_active()
        return {
            "active_count": len(active),
            "injections": active,
        }
    except Exception as e:
        print(f"[SelfImprove API Error] list_injections: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list injections: {str(e)}")


@router.get("/rollbacks")
async def list_rollback_history(limit: int = 50):
    """Full rollback history (newest first)."""
    try:
        log = RollbackLog()
        return {
            "total_active": log.count_active(),
            "history": log.list_all(limit=limit),
        }
    except Exception as e:
        print(f"[SelfImprove API Error] list_rollbacks: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list rollback history: {str(e)}")
