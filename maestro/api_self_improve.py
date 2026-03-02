"""
Self-Improvement API — REST endpoints for the rapid recursion pipeline.

Exposes the self-improvement engine through HTTP endpoints so the
Web-UI can trigger improvement cycles, inspect proposals, and
review validation results.
"""

import asyncio
from dataclasses import asdict

from fastapi import APIRouter, HTTPException

from maestro.self_improve import SelfImprovementEngine
from maestro.magi import Magi
from maestro.magi_vir import ComputeNodeRegistry, ComputeNode


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
