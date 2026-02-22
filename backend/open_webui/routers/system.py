"""
routers/system.py — System metrics + load-balancer configuration endpoints.

Endpoints:
    GET  /api/v1/system/metrics        Admin-only. CPU%, RAM%, disk%, per-backend /api/ps.
    GET  /api/v1/system/lb-strategy    Return current LB algorithm.
    POST /api/v1/system/lb-strategy    Change LB algorithm (admin only).
"""

import json
import logging
import os
from typing import Optional

import aiohttp
import psutil

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request

from open_webui.utils.auth import get_admin_user

log = logging.getLogger(__name__)

router = APIRouter()

# Valid LB strategies
LB_STRATEGIES = {"least_connections", "round_robin", "fastest"}
_LB_REDIS_KEY = "system:lb_strategy"
_LB_DEFAULT = os.environ.get("OLLAMA_LB_STRATEGY", "least_connections")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _local_metrics() -> dict:
    """Collect CPU%, RAM%, and disk% for the Open WebUI server process."""
    cpu = psutil.cpu_percent(interval=0.1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "cpu_percent": round(cpu, 1),
        "ram_total_gb": round(mem.total / 1_073_741_824, 2),
        "ram_used_gb": round(mem.used / 1_073_741_824, 2),
        "ram_percent": mem.percent,
        "disk_total_gb": round(disk.total / 1_073_741_824, 2),
        "disk_used_gb": round(disk.used / 1_073_741_824, 2),
        "disk_percent": disk.percent,
    }


async def _ollama_ps(base_url: str, timeout: int = 5) -> Optional[dict]:
    """
    Proxy a call to Ollama's /api/ps endpoint which returns currently loaded
    models and their memory usage.

    Returns the parsed JSON payload or None on error.
    """
    url = f"{base_url.rstrip('/')}/api/ps"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        log.debug(f"Ollama /api/ps call failed for {base_url}: {e}")
    return None


async def _get_lb_strategy(redis) -> str:
    """Read current LB strategy from Redis, falling back to env var."""
    if redis:
        try:
            val = await redis.get(_LB_REDIS_KEY)
            if val:
                return val.decode() if isinstance(val, bytes) else val
        except Exception:
            pass
    return _LB_DEFAULT


# ---------------------------------------------------------------------------
# Metrics endpoint
# ---------------------------------------------------------------------------

@router.get("/metrics", summary="Get system metrics (admin only)")
async def get_system_metrics(
    request: Request,
    user=Depends(get_admin_user),
):
    """
    Returns:
    - Local server CPU, RAM, disk stats (via psutil)
    - Per-Ollama-backend /api/ps data (loaded models, VRAM usage)
    """
    result = {
        "server": _local_metrics(),
        "ollama_backends": {},
    }

    ollama_enabled = getattr(
        getattr(request.app.state, "config", None), "ENABLE_OLLAMA_API", False
    )
    ollama_urls = getattr(
        getattr(request.app.state, "config", None), "OLLAMA_BASE_URLS", []
    )

    if ollama_enabled and ollama_urls:
        for url in ollama_urls:
            ps_data = await _ollama_ps(url)
            result["ollama_backends"][url] = {"api_ps": ps_data}

    return result


# ---------------------------------------------------------------------------
# B3: LB strategy endpoints
# ---------------------------------------------------------------------------


@router.get("/lb-strategy", summary="Get current Ollama load-balancing strategy")
async def get_lb_strategy(
    request: Request,
    user=Depends(get_admin_user),
):
    """
    Returns the active Ollama load-balancing algorithm.

    Strategies:
    - **least_connections** *(default)* — route to the backend with fewest active jobs
    - **round_robin** — cycle through backends in order
    - **fastest** — route to the backend with lowest average response time
    """
    redis = getattr(request.app.state, "redis", None)
    strategy = await _get_lb_strategy(redis)
    return {
        "strategy": strategy,
        "available": sorted(LB_STRATEGIES),
        "source": "redis" if redis else "env",
    }


@router.post("/lb-strategy", summary="Change Ollama load-balancing strategy (admin only)")
async def set_lb_strategy(
    request: Request,
    strategy: str = Body(..., embed=True),
    user=Depends(get_admin_user),
):
    """
    Persist a new LB strategy.  Takes effect immediately for new incoming requests.

    Body: `{"strategy": "least_connections" | "round_robin" | "fastest"}`
    """
    if strategy not in LB_STRATEGIES:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid strategy '{strategy}'. Must be one of: {sorted(LB_STRATEGIES)}",
        )

    redis = getattr(request.app.state, "redis", None)
    if redis:
        try:
            await redis.set(_LB_REDIS_KEY, strategy)
        except Exception as e:
            log.warning(f"Failed to persist LB strategy to Redis: {e}")

    # Also update env var so ollama.py picks it up in-process
    os.environ["OLLAMA_LB_STRATEGY"] = strategy

    return {"strategy": strategy, "saved": bool(redis)}


# ---------------------------------------------------------------------------
# B2: Backend history snapshots endpoint
# ---------------------------------------------------------------------------


@router.get("/snapshots", summary="Get backend metric time-series (admin only)")
async def get_backend_snapshots(
    limit: int = Query(60, ge=1, le=500, description="Max snapshots per backend"),
    since: Optional[int] = Query(None, description="Only return snapshots after this epoch second"),
    backend_url: Optional[str] = Query(None, description="Filter to a single backend URL"),
    user=Depends(get_admin_user),
):
    """
    Returns recent backend metric snapshots grouped by backend URL.

    Each backend entry is an array of snapshot objects:
    captured_at, cpu_percent, ram_percent, active_jobs, queued_jobs,
    loaded_models, vram_used_gb, avg_tokens_per_second.
    """
    from open_webui.models.backend_snapshots import BackendSnapshots

    if backend_url:
        urls = [backend_url]
    else:
        urls = BackendSnapshots.get_all_backends()

    result = {}
    for url in urls:
        snaps = BackendSnapshots.get_recent(url, limit=limit, since=since)
        result[url] = [s.model_dump() for s in snaps]

    return {"backends": result, "count": sum(len(v) for v in result.values())}
