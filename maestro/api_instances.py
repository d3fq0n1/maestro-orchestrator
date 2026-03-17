"""
API endpoints for multi-instance cluster management.

GET  /api/instances         -- list all running instances with health
POST /api/instances/spawn   -- spawn a new cluster member
POST /api/instances/{n}/stop -- stop instance N
POST /api/instances/stop-all -- stop all running instances
"""

import asyncio

from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/instances", tags=["instances"])


def _run_sync(fn, *args, **kwargs):
    """Run a blocking function in the default executor."""
    import functools
    loop = asyncio.get_running_loop()
    return loop.run_in_executor(None, functools.partial(fn, *args, **kwargs))


@router.get("")
async def list_instances():
    """Return all running instances with health status."""
    from maestro.instances import get_all_status
    instances = await _run_sync(get_all_status)
    return {
        "instances": [
            {
                "number": inst.number,
                "project": inst.project,
                "port": inst.port,
                "url": inst.url,
                "healthy": inst.healthy,
                "role": inst.role,
                "shard_index": inst.shard_index,
                "human_name": inst.human_name,
                "container_ip": inst.container_ip,
            }
            for inst in instances
        ],
        "total": len(instances),
        "healthy": sum(1 for i in instances if i.healthy),
        "shards": sum(1 for i in instances if i.role == "shard"),
    }


@router.post("/spawn")
async def spawn_instance():
    """Spawn a new cluster member (orchestrator or shard)."""
    from maestro.instances import spawn
    try:
        info = await _run_sync(spawn)
        return {
            "number": info.number,
            "project": info.project,
            "port": info.port,
            "url": info.url,
            "healthy": info.healthy,
            "role": info.role,
            "shard_index": info.shard_index,
            "human_name": info.human_name,
            "container_ip": info.container_ip,
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{n}/stop")
async def stop_instance(n: int):
    """Stop instance *n* and unregister it from the cluster."""
    from maestro.instances import stop, detect_running
    running = await _run_sync(detect_running)
    if n not in running:
        raise HTTPException(status_code=404, detail=f"Instance {n} is not running")
    try:
        await _run_sync(stop, n)
        return {"stopped": n}
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/stop-all")
async def stop_all_instances():
    """Stop all running instances and clean up shared infrastructure."""
    from maestro.instances import stop_all
    count = await _run_sync(stop_all)
    return {"stopped_count": count}
