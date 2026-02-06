# Load balancing: Implemented least-connections algorithm that selects the backend server
# with the fewest active requests. Uses Redis (if available) or in-memory tracking to monitor
# active job counts per server. Falls back to random selection if load stats are unavailable.

import asyncio
import json
import logging
import os
import random
import re
import time
from datetime import datetime

from typing import Optional, Union
from urllib.parse import urlparse
import aiohttp
from aiocache import cached
import requests

from open_webui.utils.headers import include_user_info_headers
from open_webui.models.chats import Chats
from open_webui.models.users import UserModel

from open_webui.env import (
    ENABLE_FORWARD_USER_INFO_HEADERS,
    REDIS_KEY_PREFIX,
    OLLAMA_LB_ACTIVE_JOBS_WEIGHT,
    OLLAMA_LB_RESPONSE_TIME_WEIGHT,
    OLLAMA_HEALTH_CHECK_INTERVAL,
    OLLAMA_HEALTH_CHECK_TIMEOUT,
    OLLAMA_ALERT_RESPONSE_TIME_THRESHOLD_MS,
    OLLAMA_ALERT_ACTIVE_JOBS_THRESHOLD,
)

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    APIRouter,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, validator
from starlette.background import BackgroundTask
from sqlalchemy.orm import Session

from open_webui.internal.db import get_session


from open_webui.models.models import Models
from open_webui.utils.misc import (
    calculate_sha256,
)
from open_webui.utils.payload import (
    apply_model_params_to_body_ollama,
    apply_model_params_to_body_openai,
    apply_system_prompt_to_body,
)
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_access


from open_webui.config import (
    UPLOAD_DIR,
)
from open_webui.env import (
    ENV,
    MODELS_CACHE_TTL,
    AIOHTTP_CLIENT_SESSION_SSL,
    AIOHTTP_CLIENT_TIMEOUT,
    AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST,
    BYPASS_MODEL_ACCESS_CONTROL,
)
from open_webui.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)


##########################################
#
# Job Tracking
#
##########################################

ACTIVE_JOB_STATS = {}
PERFORMANCE_STATS = {}  # {base_url: {"avg_response_time": float, "sample_count": int}}
HEALTH_STATUS = {}  # {base_url: {"status": "healthy" | "unhealthy", "last_check": timestamp}}


async def check_server_health(base_url, timeout=OLLAMA_HEALTH_CHECK_TIMEOUT):
    """
    Check if a server is healthy by pinging its /api/version endpoint.
    Returns True if healthy, False otherwise.
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{base_url}/api/version",
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                return response.status == 200
    except Exception as e:
        log.debug(f"Health check failed for {base_url}: {e}")
        return False


async def update_health_status(base_url, is_healthy, request: Request = None):
    """
    Update the health status of a server in Redis or in-memory storage.
    """
    status = "healthy" if is_healthy else "unhealthy"
    timestamp = time.time()
    
    if request and hasattr(request.app.state, "redis") and request.app.state.redis:
        try:
            key = f"health_status:{base_url}"
            data = json.dumps({"status": status, "last_check": timestamp})
            # TTL of 120 seconds (2x health check interval)
            await request.app.state.redis.set(key, data, ex=120)
        except Exception as e:
            log.error(f"Redis error updating health status: {e}")
            HEALTH_STATUS[base_url] = {"status": status, "last_check": timestamp}
    else:
        HEALTH_STATUS[base_url] = {"status": status, "last_check": timestamp}


async def get_health_status(base_url, request: Request = None):
    """
    Get the health status of a server from Redis or in-memory storage.
    Returns "healthy", "unhealthy", or "unknown".
    """
    if request and hasattr(request.app.state, "redis") and request.app.state.redis:
        try:
            key = f"health_status:{base_url}"
            data = await request.app.state.redis.get(key)
            if data:
                status_data = json.loads(data)
                return status_data.get("status", "unknown")
        except Exception as e:
            log.debug(f"Redis error reading health status: {e}")
            return HEALTH_STATUS.get(base_url, {}).get("status", "unknown")
    else:
        return HEALTH_STATUS.get(base_url, {}).get("status", "unknown")


async def update_active_job_count(url, delta=1, request: Request = None):
    # Extract base URL to group endpoints provided by the same server
    # e.g. http://localhost:11434/api/chat -> http://localhost:11434
    try:
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    except Exception:
        base_url = url

    if request and hasattr(request.app.state, "redis") and request.app.state.redis:
        try:
            key = f"active_jobs:{base_url}"
            if delta > 0:
                await request.app.state.redis.incr(key, delta)
            else:
                # Decrement but don't go below 0
                val = await request.app.state.redis.decr(key, -delta)
                if val < 0:
                     await request.app.state.redis.set(key, 0)
        except Exception as e:
            log.error(f"Redis error updating job count: {e}")
    else:
        # Fallback to in-memory matching
        if base_url not in ACTIVE_JOB_STATS:
            ACTIVE_JOB_STATS[base_url] = 0
        ACTIVE_JOB_STATS[base_url] += delta
        if ACTIVE_JOB_STATS[base_url] < 0:
             ACTIVE_JOB_STATS[base_url] = 0
        
        # Check alert threshold (only when incrementing)
        if delta > 0 and ACTIVE_JOB_STATS[base_url] > OLLAMA_ALERT_ACTIVE_JOBS_THRESHOLD:
            log.warning(
                f"Server {base_url} active jobs ({ACTIVE_JOB_STATS[base_url]}) "
                f"exceeds threshold ({OLLAMA_ALERT_ACTIVE_JOBS_THRESHOLD})"
            )


async def update_response_time(url, response_time_ms, request: Request = None):
    """
    Update the moving average response time for a server.
    Uses exponential moving average with alpha=0.3 (30% weight to new sample).
    """
    try:
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    except Exception:
        base_url = url
    
    alpha = 0.3  # Weight for new sample (30% new, 70% historical)
    
    if request and hasattr(request.app.state, "redis") and request.app.state.redis:
        try:
            key = f"perf_avg_response_time:{base_url}"
            count_key = f"perf_sample_count:{base_url}"
            
            # Get current average and count
            current_avg = await request.app.state.redis.get(key)
            current_avg = float(current_avg) if current_avg else 0.0
            
            count = await request.app.state.redis.get(count_key)
            count = int(count) if count else 0
            
            # Calculate exponential moving average
            if count == 0:
                new_avg = response_time_ms
            else:
                new_avg = (alpha * response_time_ms) + ((1 - alpha) * current_avg)
            
            # Store updated values with 1 hour TTL
            await request.app.state.redis.set(key, str(new_avg), ex=3600)
            await request.app.state.redis.incr(count_key)
            await request.app.state.redis.expire(count_key, 3600)
            
        except Exception as e:
            log.debug(f"Redis error updating response time: {e}")
            # Fallback to in-memory
            _update_response_time_memory(base_url, response_time_ms, alpha)
    else:
        # In-memory fallback
        _update_response_time_memory(base_url, response_time_ms, alpha)
    
    # Check alert thresholds

    if response_time_ms > OLLAMA_ALERT_RESPONSE_TIME_THRESHOLD_MS:
        log.warning(
            f"Server {base_url} response time ({response_time_ms:.2f}ms) "
            f"exceeds threshold ({OLLAMA_ALERT_RESPONSE_TIME_THRESHOLD_MS}ms)"
        )


async def update_token_stats(url, eval_count, eval_duration_nanos, request: Request = None):
    """
    Update the moving average tokens per second for a server.
    """
    try:
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    except Exception:
        base_url = url
    
    # Calculate tokens per second (eval_duration is in nanoseconds)
    if eval_duration_nanos <= 0:
        return
    
    tokens_per_second = eval_count / (eval_duration_nanos / 1_000_000_000.0)
    
    # Check for reasonable bounds (e.g. 0.1 to 500 t/s) to filter outliers
    if tokens_per_second < 0.1 or tokens_per_second > 1000:
        return

    alpha = 0.3  # Weight for new sample
    
    if request and hasattr(request.app.state, "redis") and request.app.state.redis:
        try:
            key = f"perf_avg_tokens_per_second:{base_url}"
            
            # Get current average
            current_avg = await request.app.state.redis.get(key)
            current_avg = float(current_avg) if current_avg else 0.0
            
            # Calculate exponential moving average
            if current_avg == 0:
                new_avg = tokens_per_second
            else:
                new_avg = (alpha * tokens_per_second) + ((1 - alpha) * current_avg)
            
            # Store updated values with 1 hour TTL
            await request.app.state.redis.set(key, str(new_avg), ex=3600)
            
        except Exception as e:
            log.debug(f"Redis error updating token stats: {e}")
            _update_token_stats_memory(base_url, tokens_per_second, alpha)
    else:
        _update_token_stats_memory(base_url, tokens_per_second, alpha)


def _update_token_stats_memory(base_url, tokens_per_second, alpha):
    if base_url not in PERFORMANCE_STATS:
        PERFORMANCE_STATS[base_url] = PERFORMANCE_STATS.get(base_url, {})
        PERFORMANCE_STATS[base_url]["avg_tokens_per_second"] = tokens_per_second
    else:
        current_avg = PERFORMANCE_STATS[base_url].get("avg_tokens_per_second", 0.0)
        if current_avg == 0:
            new_avg = tokens_per_second
        else:
            new_avg = (alpha * tokens_per_second) + ((1 - alpha) * current_avg)
        PERFORMANCE_STATS[base_url]["avg_tokens_per_second"] = new_avg


def _update_response_time_memory(base_url, response_time_ms, alpha):
    """Helper function for in-memory response time tracking."""
    if base_url not in PERFORMANCE_STATS:
        PERFORMANCE_STATS[base_url] = {"avg_response_time": response_time_ms, "sample_count": 1}
    else:
        current_avg = PERFORMANCE_STATS[base_url]["avg_response_time"]
        new_avg = (alpha * response_time_ms) + ((1 - alpha) * current_avg)
        PERFORMANCE_STATS[base_url]["avg_response_time"] = new_avg
        PERFORMANCE_STATS[base_url]["sample_count"] += 1


##########################################
#
# Utility functions
#
##########################################


async def send_get_request(url, key=None, user: UserModel = None):
    timeout = aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST)
    try:
        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            headers = {
                "Content-Type": "application/json",
                **({"Authorization": f"Bearer {key}"} if key else {}),
            }

            if ENABLE_FORWARD_USER_INFO_HEADERS and user:
                headers = include_user_info_headers(headers, user)

            async with session.get(
                url,
                headers=headers,
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as response:
                return await response.json()
    except Exception as e:
        # Handle connection error here
        log.error(f"Connection error: {e}")
        return None


async def cleanup_response(
    response: Optional[aiohttp.ClientResponse],
    session: Optional[aiohttp.ClientSession],
):
    if response:
        response.close()
    if session:
        await session.close()


async def send_post_request(
    url: str,
    payload: Union[str, bytes],
    stream: bool = True,
    key: Optional[str] = None,
    content_type: Optional[str] = None,
    user: UserModel = None,
    metadata: Optional[dict] = None,
    request: Optional[Request] = None,
):
    await update_active_job_count(url, 1, request)
    decremented = False
    start_time = time.time()  # Track request start time

    async def decrement_counter():
        nonlocal decremented
        if not decremented:
             await update_active_job_count(url, -1, request)
             decremented = True
             
             # Record response time
             response_time_ms = (time.time() - start_time) * 1000
             await update_response_time(url, response_time_ms, request)

    r = None
    try:
        session = aiohttp.ClientSession(
            trust_env=True, timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT)
        )

        headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {key}"} if key else {}),
        }

        if ENABLE_FORWARD_USER_INFO_HEADERS and user:
            headers = include_user_info_headers(headers, user)
            if metadata and metadata.get("chat_id"):
                headers["X-OpenWebUI-Chat-Id"] = metadata.get("chat_id")

        r = await session.post(
            url,
            data=payload,
            headers=headers,
            ssl=AIOHTTP_CLIENT_SESSION_SSL,
        )

        if r.ok is False:
            try:
                res = await r.json()
                await cleanup_response(r, session)
                if "error" in res:
                    raise HTTPException(status_code=r.status, detail=res["error"])
            except HTTPException as e:
                raise e  # Re-raise HTTPException to be handled by FastAPI
            except Exception as e:
                log.error(f"Failed to parse error response: {e}")
                raise HTTPException(
                    status_code=r.status,
                    detail=f"Open WebUI: Server Connection Error",
                )

        r.raise_for_status()  # Raises an error for bad responses (4xx, 5xx)
        if stream:
            response_headers = dict(r.headers)

            if content_type:
                response_headers["Content-Type"] = content_type

            async def stream_wrapper():
                try:
                    async for chunk in r.content.iter_any():
                        yield chunk
                        # Try to extract metrics from the chunk (usually the last one)
                        try:
                            # Iterate through potential multiple JSON objects in one chunk
                            # This is a simple heuristic; robust parsing might be needed for complex cases
                            # But Ollama usually sends clean JSON lines
                            decoded = chunk.decode("utf-8", errors="ignore")
                            # We search for the "done": true block which contains metrics
                            if '"done":true' in decoded.replace(" ", ""):
                                # Parse the last valid JSON object
                                lines = decoded.strip().split("\n")
                                for line in lines:
                                    if '"done":true' in line.replace(" ", "") or '"done": true' in line:
                                        data = json.loads(line)
                                        if "eval_count" in data and "eval_duration" in data:
                                            await update_token_stats(
                                                url, 
                                                data["eval_count"], 
                                                data["eval_duration"], 
                                                request
                                            )
                        except Exception:
                            pass # Don't break stream on parsing error
                finally:
                    await cleanup_response(r, session)
                    await decrement_counter()

            return StreamingResponse(
                stream_wrapper(),
                status_code=r.status,
                headers=response_headers,
                background=None, # Background task moved to finally block of wrapper
            )
        else:
            res = await r.json()
            await decrement_counter()
            
            # Non-streaming update
            if "eval_count" in res and "eval_duration" in res:
                await update_token_stats(url, res["eval_count"], res["eval_duration"], request)
                
            return res

    except HTTPException as e:
        await decrement_counter()
        raise e  # Re-raise HTTPException to be handled by FastAPI
    except Exception as e:
        await decrement_counter()
        detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status if r else 500,
            detail=detail if e else "Open WebUI: Server Connection Error",
        )
    finally:
        if not stream and r:
             await cleanup_response(r, session)


def get_api_key(idx, url, configs):
    parsed_url = urlparse(url)
    base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
    return configs.get(str(idx), configs.get(base_url, {})).get(
        "key", None
    )  # Legacy support


##########################################
#
# API routes
#
##########################################

router = APIRouter()


@router.head("/")
@router.get("/")
async def get_status():
    return {"status": True}


@router.get("/api/load-stats")
async def get_load_stats(request: Request, user=Depends(get_admin_user)):
    """
    Get active job counts per Ollama backend server.
    Returns a dictionary mapping server URLs to their active job counts.
    """
    stats = {}
    
    if not request.app.state.config.ENABLE_OLLAMA_API:
        return stats
    
    for url in request.app.state.config.OLLAMA_BASE_URLS:
        # Parse to get base URL
        try:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        except Exception:
            base_url = url
        
        # Try to get from Redis first
        if hasattr(request.app.state, "redis") and request.app.state.redis:
            try:
                key = f"active_jobs:{base_url}"
                count = await request.app.state.redis.get(key)
                stats[base_url] = int(count) if count else 0
            except Exception as e:
                log.error(f"Redis error reading job count: {e}")
                stats[base_url] = ACTIVE_JOB_STATS.get(base_url, 0)
        else:
            # Fallback to in-memory
            stats[base_url] = ACTIVE_JOB_STATS.get(base_url, 0)
    
    return stats


@router.get("/api/server-stats")
async def get_server_stats(request: Request, user=Depends(get_admin_user)):
    """
    Get comprehensive performance metrics per Ollama backend server.
    Returns active job counts and average response times.
    """
    stats = {}
    
    if not request.app.state.config.ENABLE_OLLAMA_API:
        return stats
    
    for url in request.app.state.config.OLLAMA_BASE_URLS:
        # Parse to get base URL
        try:
            parsed_url = urlparse(url)
            base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        except Exception:
            base_url = url
        
        # Get active jobs
        active_jobs = 0
        if hasattr(request.app.state, "redis") and request.app.state.redis:
            try:
                key = f"active_jobs:{base_url}"
                count = await request.app.state.redis.get(key)
                active_jobs = int(count) if count else 0
            except Exception:
                active_jobs = ACTIVE_JOB_STATS.get(base_url, 0)
        else:
            active_jobs = ACTIVE_JOB_STATS.get(base_url, 0)
        
        # Get average response time
        avg_response_time = 0.0
        sample_count = 0
        if hasattr(request.app.state, "redis") and request.app.state.redis:
            try:
                time_key = f"perf_avg_response_time:{base_url}"
                count_key = f"perf_sample_count:{base_url}"
                token_key = f"perf_avg_tokens_per_second:{base_url}"
                
                avg_time = await request.app.state.redis.get(time_key)
                avg_response_time = float(avg_time) if avg_time else 0.0
                
                count = await request.app.state.redis.get(count_key)
                sample_count = int(count) if count else 0

                avg_tokens = await request.app.state.redis.get(token_key)
                avg_tokens_per_second = float(avg_tokens) if avg_tokens else 0.0
            except Exception:
                perf_data = PERFORMANCE_STATS.get(base_url, {})
                avg_response_time = perf_data.get("avg_response_time", 0.0)
                sample_count = perf_data.get("sample_count", 0)
                avg_tokens_per_second = perf_data.get("avg_tokens_per_second", 0.0)
        else:
            perf_data = PERFORMANCE_STATS.get(base_url, {})
            avg_response_time = perf_data.get("avg_response_time", 0.0)
            sample_count = perf_data.get("sample_count", 0)
            avg_tokens_per_second = perf_data.get("avg_tokens_per_second", 0.0)
        
        # Get health status
        health_status = await get_health_status(base_url, request)
        
        stats[base_url] = {
            "active_jobs": active_jobs,
            "avg_response_time_ms": round(avg_response_time, 2),
            "avg_tokens_per_second": round(avg_tokens_per_second, 2),
            "sample_count": sample_count,
            "health_status": health_status
        }
    
    return stats

class ConnectionVerificationForm(BaseModel):
    url: str
    key: Optional[str] = None


@router.post("/verify")
async def verify_connection(
    form_data: ConnectionVerificationForm, user=Depends(get_admin_user)
):
    url = form_data.url
    key = form_data.key

    async with aiohttp.ClientSession(
        trust_env=True,
        timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT_MODEL_LIST),
    ) as session:
        try:
            headers = {
                **({"Authorization": f"Bearer {key}"} if key else {}),
            }

            if ENABLE_FORWARD_USER_INFO_HEADERS and user:
                headers = include_user_info_headers(headers, user)

            async with session.get(
                f"{url}/api/version",
                headers=headers,
                ssl=AIOHTTP_CLIENT_SESSION_SSL,
            ) as r:
                if r.status != 200:
                    detail = f"HTTP Error: {r.status}"
                    res = await r.json()

                    if "error" in res:
                        detail = f"External Error: {res['error']}"
                    raise Exception(detail)

                data = await r.json()
                return data
        except aiohttp.ClientError as e:
            log.exception(f"Client error: {str(e)}")
            raise HTTPException(
                status_code=500, detail="Open WebUI: Server Connection Error"
            )
        except Exception as e:
            log.exception(f"Unexpected error: {e}")
            error_detail = f"Unexpected error: {str(e)}"
            raise HTTPException(status_code=500, detail=error_detail)


@router.get("/config")
async def get_config(request: Request, user=Depends(get_admin_user)):
    return {
        "ENABLE_OLLAMA_API": request.app.state.config.ENABLE_OLLAMA_API,
        "OLLAMA_BASE_URLS": request.app.state.config.OLLAMA_BASE_URLS,
        "OLLAMA_API_CONFIGS": request.app.state.config.OLLAMA_API_CONFIGS,
    }


class OllamaConfigForm(BaseModel):
    ENABLE_OLLAMA_API: Optional[bool] = None
    OLLAMA_BASE_URLS: list[str]
    OLLAMA_API_CONFIGS: dict


@router.post("/config/update")
async def update_config(
    request: Request, form_data: OllamaConfigForm, user=Depends(get_admin_user)
):
    request.app.state.config.ENABLE_OLLAMA_API = form_data.ENABLE_OLLAMA_API

    request.app.state.config.OLLAMA_BASE_URLS = form_data.OLLAMA_BASE_URLS
    request.app.state.config.OLLAMA_API_CONFIGS = form_data.OLLAMA_API_CONFIGS

    # Remove the API configs that are not in the API URLS
    keys = list(map(str, range(len(request.app.state.config.OLLAMA_BASE_URLS))))
    request.app.state.config.OLLAMA_API_CONFIGS = {
        key: value
        for key, value in request.app.state.config.OLLAMA_API_CONFIGS.items()
        if key in keys
    }

    return {
        "ENABLE_OLLAMA_API": request.app.state.config.ENABLE_OLLAMA_API,
        "OLLAMA_BASE_URLS": request.app.state.config.OLLAMA_BASE_URLS,
        "OLLAMA_API_CONFIGS": request.app.state.config.OLLAMA_API_CONFIGS,
    }


def merge_ollama_models_lists(model_lists):
    merged_models = {}

    for idx, model_list in enumerate(model_lists):
        if model_list is not None:
            for model in model_list:
                id = model.get("model")
                if id is not None:
                    if id not in merged_models:
                        model["urls"] = [idx]
                        merged_models[id] = model
                    else:
                        merged_models[id]["urls"].append(idx)

    return list(merged_models.values())


@cached(
    ttl=MODELS_CACHE_TTL,
    key=lambda _, user: f"ollama_all_models_{user.id}" if user else "ollama_all_models",
)
async def get_all_models(request: Request, user: UserModel = None):
    log.info("get_all_models()")
    if request.app.state.config.ENABLE_OLLAMA_API:
        request_tasks = []
        for idx, url in enumerate(request.app.state.config.OLLAMA_BASE_URLS):
            if (str(idx) not in request.app.state.config.OLLAMA_API_CONFIGS) and (
                url not in request.app.state.config.OLLAMA_API_CONFIGS  # Legacy support
            ):
                request_tasks.append(send_get_request(f"{url}/api/tags", user=user))
            else:
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                )

                enable = api_config.get("enable", True)
                key = api_config.get("key", None)

                if enable:
                    request_tasks.append(
                        send_get_request(f"{url}/api/tags", key, user=user)
                    )
                else:
                    request_tasks.append(asyncio.ensure_future(asyncio.sleep(0, None)))

        responses = await asyncio.gather(*request_tasks)

        for idx, response in enumerate(responses):
            if response:
                url = request.app.state.config.OLLAMA_BASE_URLS[idx]
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                )

                connection_type = api_config.get("connection_type", "local")

                prefix_id = api_config.get("prefix_id", None)
                tags = api_config.get("tags", [])
                model_ids = api_config.get("model_ids", [])

                if len(model_ids) != 0 and "models" in response:
                    response["models"] = list(
                        filter(
                            lambda model: model["model"] in model_ids,
                            response["models"],
                        )
                    )

                for model in response.get("models", []):
                    if prefix_id:
                        model["model"] = f"{prefix_id}.{model['model']}"

                    if tags:
                        model["tags"] = tags

                    if connection_type:
                        model["connection_type"] = connection_type

        models = {
            "models": merge_ollama_models_lists(
                map(
                    lambda response: response.get("models", []) if response else None,
                    responses,
                )
            )
        }

        try:
            loaded_models = await get_ollama_loaded_models(request, user=user)
            expires_map = {
                m["model"]: m["expires_at"]
                for m in loaded_models["models"]
                if "expires_at" in m
            }

            for m in models["models"]:
                if m["model"] in expires_map:
                    # Parse ISO8601 datetime with offset, get unix timestamp as int
                    dt = datetime.fromisoformat(expires_map[m["model"]])
                    m["expires_at"] = int(dt.timestamp())
        except Exception as e:
            log.debug(f"Failed to get loaded models: {e}")

    else:
        models = {"models": []}

    request.app.state.OLLAMA_MODELS = {
        model["model"]: model for model in models["models"]
    }
    return models


async def get_filtered_models(models, user, db=None):
    # Filter models based on user access control
    filtered_models = []
    for model in models.get("models", []):
        model_info = Models.get_model_by_id(model["model"], db=db)
        if model_info:
            if user.id == model_info.user_id or has_access(
                user.id, type="read", access_control=model_info.access_control, db=db
            ):
                filtered_models.append(model)
    return filtered_models


@router.get("/api/tags")
@router.get("/api/tags/{url_idx}")
async def get_ollama_tags(
    request: Request, url_idx: Optional[int] = None, user=Depends(get_verified_user)
):
    models = []

    if url_idx is None:
        models = await get_all_models(request, user=user)
    else:
        url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
        key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

        r = None
        try:
            headers = {
                **({"Authorization": f"Bearer {key}"} if key else {}),
            }

            if ENABLE_FORWARD_USER_INFO_HEADERS and user:
                headers = include_user_info_headers(headers, user)

            r = requests.request(
                method="GET",
                url=f"{url}/api/tags",
                headers=headers,
            )
            r.raise_for_status()

            models = r.json()
        except Exception as e:
            log.exception(e)

            detail = None
            if r is not None:
                try:
                    res = r.json()
                    if "error" in res:
                        detail = f"Ollama: {res['error']}"
                except Exception:
                    detail = f"Ollama: {e}"

            raise HTTPException(
                status_code=r.status_code if r else 500,
                detail=detail if detail else "Open WebUI: Server Connection Error",
            )

    if user.role == "user" and not BYPASS_MODEL_ACCESS_CONTROL:
        models["models"] = await get_filtered_models(models, user)

    return models


@router.get("/api/ps")
async def get_ollama_loaded_models(request: Request, user=Depends(get_admin_user)):
    """
    List models that are currently loaded into Ollama memory, and which node they are loaded on.
    """
    if request.app.state.config.ENABLE_OLLAMA_API:
        request_tasks = []
        for idx, url in enumerate(request.app.state.config.OLLAMA_BASE_URLS):
            if (str(idx) not in request.app.state.config.OLLAMA_API_CONFIGS) and (
                url not in request.app.state.config.OLLAMA_API_CONFIGS  # Legacy support
            ):
                request_tasks.append(send_get_request(f"{url}/api/ps", user=user))
            else:
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                )

                enable = api_config.get("enable", True)
                key = api_config.get("key", None)

                if enable:
                    request_tasks.append(
                        send_get_request(f"{url}/api/ps", key, user=user)
                    )
                else:
                    request_tasks.append(asyncio.ensure_future(asyncio.sleep(0, None)))

        responses = await asyncio.gather(*request_tasks)

        for idx, response in enumerate(responses):
            if response:
                url = request.app.state.config.OLLAMA_BASE_URLS[idx]
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                )

                prefix_id = api_config.get("prefix_id", None)

                for model in response.get("models", []):
                    if prefix_id:
                        model["model"] = f"{prefix_id}.{model['model']}"

        models = {
            "models": merge_ollama_models_lists(
                map(
                    lambda response: response.get("models", []) if response else None,
                    responses,
                )
            )
        }
    else:
        models = {"models": []}

    return models


@router.get("/api/version")
@router.get("/api/version/{url_idx}")
async def get_ollama_versions(request: Request, url_idx: Optional[int] = None):
    if request.app.state.config.ENABLE_OLLAMA_API:
        if url_idx is None:
            # returns lowest version
            request_tasks = []

            for idx, url in enumerate(request.app.state.config.OLLAMA_BASE_URLS):
                api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
                    str(idx),
                    request.app.state.config.OLLAMA_API_CONFIGS.get(
                        url, {}
                    ),  # Legacy support
                )

                enable = api_config.get("enable", True)
                key = api_config.get("key", None)

                if enable:
                    request_tasks.append(
                        send_get_request(
                            f"{url}/api/version",
                            key,
                        )
                    )

            responses = await asyncio.gather(*request_tasks)
            responses = list(filter(lambda x: x is not None, responses))

            if len(responses) > 0:
                lowest_version = min(
                    responses,
                    key=lambda x: tuple(
                        map(int, re.sub(r"^v|-.*", "", x["version"]).split("."))
                    ),
                )

                return {"version": lowest_version["version"]}
            else:
                raise HTTPException(
                    status_code=500,
                    detail=ERROR_MESSAGES.OLLAMA_NOT_FOUND,
                )
        else:
            url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

            r = None
            try:
                r = requests.request(method="GET", url=f"{url}/api/version")
                r.raise_for_status()

                return r.json()
            except Exception as e:
                log.exception(e)

                detail = None
                if r is not None:
                    try:
                        res = r.json()
                        if "error" in res:
                            detail = f"Ollama: {res['error']}"
                    except Exception:
                        detail = f"Ollama: {e}"

                raise HTTPException(
                    status_code=r.status_code if r else 500,
                    detail=detail if detail else "Open WebUI: Server Connection Error",
                )
    else:
        return {"version": False}


class ModelNameForm(BaseModel):
    model: Optional[str] = None
    model_config = ConfigDict(
        extra="allow",
    )


@router.post("/api/unload")
async def unload_model(
    request: Request,
    form_data: ModelNameForm,
    user=Depends(get_admin_user),
):
    form_data = form_data.model_dump(exclude_none=True)
    model_name = form_data.get("model", form_data.get("name"))

    if not model_name:
        raise HTTPException(
            status_code=400, detail="Missing name of the model to unload."
        )

    # Refresh/load models if needed, get mapping from name to URLs
    await get_all_models(request, user=user)
    models = request.app.state.OLLAMA_MODELS

    # Canonicalize model name (if not supplied with version)
    if ":" not in model_name:
        model_name = f"{model_name}:latest"

    if model_name not in models:
        raise HTTPException(
            status_code=400, detail=ERROR_MESSAGES.MODEL_NOT_FOUND(model_name)
        )
    url_indices = models[model_name]["urls"]

    # Send unload to ALL url_indices
    results = []
    errors = []
    for idx in url_indices:
        url = request.app.state.config.OLLAMA_BASE_URLS[idx]
        api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
            str(idx), request.app.state.config.OLLAMA_API_CONFIGS.get(url, {})
        )
        key = get_api_key(idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

        prefix_id = api_config.get("prefix_id", None)
        if prefix_id and model_name.startswith(f"{prefix_id}."):
            model_name = model_name[len(f"{prefix_id}.") :]

        payload = {"model": model_name, "keep_alive": 0, "prompt": ""}

        try:
            res = await send_post_request(
                url=f"{url}/api/generate",
                payload=json.dumps(payload),
                stream=False,
                key=key,
                user=user,
            )
            results.append({"url_idx": idx, "success": True, "response": res})
        except Exception as e:
            log.exception(f"Failed to unload model on node {idx}: {e}")
            errors.append({"url_idx": idx, "success": False, "error": str(e)})

    if len(errors) > 0:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to unload model on {len(errors)} nodes: {errors}",
        )

    return {"status": True}


@router.post("/api/pull")
@router.post("/api/pull/{url_idx}")
async def pull_model(
    request: Request,
    form_data: ModelNameForm,
    url_idx: int = 0,
    user=Depends(get_admin_user),
):
    form_data = form_data.model_dump(exclude_none=True)
    form_data["model"] = form_data.get("model", form_data.get("name"))

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    log.info(f"url: {url}")

    # Admin should be able to pull models from any source
    payload = {**form_data, "insecure": True}

    return await send_post_request(
        url=f"{url}/api/pull",
        payload=json.dumps(payload),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
    )


class PushModelForm(BaseModel):
    model: str
    insecure: Optional[bool] = None
    stream: Optional[bool] = None


@router.delete("/api/push")
@router.delete("/api/push/{url_idx}")
async def push_model(
    request: Request,
    form_data: PushModelForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        if form_data.model in models:
            url_idx = models[form_data.model]["urls"][0]
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    log.debug(f"url: {url}")

    return await send_post_request(
        url=f"{url}/api/push",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
    )


class CreateModelForm(BaseModel):
    model: Optional[str] = None
    stream: Optional[bool] = None
    path: Optional[str] = None

    model_config = ConfigDict(extra="allow")


@router.post("/api/create")
@router.post("/api/create/{url_idx}")
async def create_model(
    request: Request,
    form_data: CreateModelForm,
    url_idx: int = 0,
    user=Depends(get_admin_user),
):
    log.debug(f"form_data: {form_data}")
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

    return await send_post_request(
        url=f"{url}/api/create",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
    )


class CopyModelForm(BaseModel):
    source: str
    destination: str


@router.post("/api/copy")
@router.post("/api/copy/{url_idx}")
async def copy_model(
    request: Request,
    form_data: CopyModelForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        if form_data.source in models:
            url_idx = models[form_data.source]["urls"][0]
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.source),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {key}"} if key else {}),
        }

        if ENABLE_FORWARD_USER_INFO_HEADERS and user:
            headers = include_user_info_headers(headers, user)

        r = requests.request(
            method="POST",
            url=f"{url}/api/copy",
            headers=headers,
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        log.debug(f"r.text: {r.text}")
        return True
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


@router.delete("/api/delete")
@router.delete("/api/delete/{url_idx}")
async def delete_model(
    request: Request,
    form_data: ModelNameForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    form_data = form_data.model_dump(exclude_none=True)
    form_data["model"] = form_data.get("model", form_data.get("name"))

    model = form_data.get("model")

    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        if model in models:
            url_idx = models[model]["urls"][0]
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    r = None
    try:
        headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {key}"} if key else {}),
        }

        if ENABLE_FORWARD_USER_INFO_HEADERS and user:
            headers = include_user_info_headers(headers, user)

        r = requests.request(
            method="DELETE",
            url=f"{url}/api/delete",
            headers=headers,
            json=form_data,
        )
        r.raise_for_status()

        log.debug(f"r.text: {r.text}")
        return True
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


@router.post("/api/show")
async def show_model_info(
    request: Request, form_data: ModelNameForm, user=Depends(get_verified_user)
):
    form_data = form_data.model_dump(exclude_none=True)
    form_data["model"] = form_data.get("model", form_data.get("name"))

    await get_all_models(request, user=user)
    models = request.app.state.OLLAMA_MODELS

    model = form_data.get("model")

    if model not in models:
        raise HTTPException(
            status_code=400,
            detail=ERROR_MESSAGES.MODEL_NOT_FOUND(model),
        )

    url_idx = random.choice(models[model]["urls"])

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    try:
        headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {key}"} if key else {}),
        }

        if ENABLE_FORWARD_USER_INFO_HEADERS and user:
            headers = include_user_info_headers(headers, user)

        r = requests.request(
            method="POST", url=f"{url}/api/show", headers=headers, json=form_data
        )
        r.raise_for_status()

        return r.json()
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


class GenerateEmbedForm(BaseModel):
    model: str
    input: list[str] | str
    truncate: Optional[bool] = None
    options: Optional[dict] = None
    keep_alive: Optional[Union[int, str]] = None

    model_config = ConfigDict(
        extra="allow",
    )


@router.post("/api/embed")
@router.post("/api/embed/{url_idx}")
async def embed(
    request: Request,
    form_data: GenerateEmbedForm,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    log.info(f"generate_ollama_batch_embeddings {form_data}")

    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        form_data.model = form_data.model.replace(f"{prefix_id}.", "")

    try:
        headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {key}"} if key else {}),
        }

        if ENABLE_FORWARD_USER_INFO_HEADERS and user:
            headers = include_user_info_headers(headers, user)

        r = requests.request(
            method="POST",
            url=f"{url}/api/embed",
            headers=headers,
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        data = r.json()
        return data
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


class GenerateEmbeddingsForm(BaseModel):
    model: str
    prompt: str
    options: Optional[dict] = None
    keep_alive: Optional[Union[int, str]] = None


@router.post("/api/embeddings")
@router.post("/api/embeddings/{url_idx}")
async def embeddings(
    request: Request,
    form_data: GenerateEmbeddingsForm,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    log.info(f"generate_ollama_embeddings {form_data}")

    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )
    key = get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS)

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        form_data.model = form_data.model.replace(f"{prefix_id}.", "")

    try:
        headers = {
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {key}"} if key else {}),
        }

        if ENABLE_FORWARD_USER_INFO_HEADERS and user:
            headers = include_user_info_headers(headers, user)

        r = requests.request(
            method="POST",
            url=f"{url}/api/embeddings",
            headers=headers,
            data=form_data.model_dump_json(exclude_none=True).encode(),
        )
        r.raise_for_status()

        data = r.json()
        return data
    except Exception as e:
        log.exception(e)

        detail = None
        if r is not None:
            try:
                res = r.json()
                if "error" in res:
                    detail = f"Ollama: {res['error']}"
            except Exception:
                detail = f"Ollama: {e}"

        raise HTTPException(
            status_code=r.status_code if r else 500,
            detail=detail if detail else "Open WebUI: Server Connection Error",
        )


class GenerateCompletionForm(BaseModel):
    model: str
    prompt: str
    suffix: Optional[str] = None
    images: Optional[list[str]] = None
    format: Optional[Union[dict, str]] = None
    options: Optional[dict] = None
    system: Optional[str] = None
    template: Optional[str] = None
    context: Optional[list[int]] = None
    stream: Optional[bool] = True
    raw: Optional[bool] = None
    keep_alive: Optional[Union[int, str]] = None


@router.post("/api/generate")
@router.post("/api/generate/{url_idx}")
async def generate_completion(
    request: Request,
    form_data: GenerateCompletionForm,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
):
    if url_idx is None:
        await get_all_models(request, user=user)
        models = request.app.state.OLLAMA_MODELS

        model = form_data.model

        if ":" not in model:
            model = f"{model}:latest"

        if model in models:
            url_idx = random.choice(models[model]["urls"])
        else:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(form_data.model),
            )

    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        form_data.model = form_data.model.replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/api/generate",
        payload=form_data.model_dump_json(exclude_none=True).encode(),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
        request=request,
    )


class ChatMessage(BaseModel):
    role: str
    content: Optional[str] = None
    tool_calls: Optional[list[dict]] = None
    images: Optional[list[str]] = None

    @validator("content", pre=True)
    @classmethod
    def check_at_least_one_field(cls, field_value, values, **kwargs):
        # Raise an error if both 'content' and 'tool_calls' are None
        if field_value is None and (
            "tool_calls" not in values or values["tool_calls"] is None
        ):
            raise ValueError(
                "At least one of 'content' or 'tool_calls' must be provided"
            )

        return field_value


class GenerateChatCompletionForm(BaseModel):
    model: str
    messages: list[ChatMessage]
    format: Optional[Union[dict, str]] = None
    options: Optional[dict] = None
    template: Optional[str] = None
    stream: Optional[bool] = True
    keep_alive: Optional[Union[int, str]] = None
    tools: Optional[list[dict]] = None
    model_config = ConfigDict(
        extra="allow",
    )


async def get_ollama_url(request: Request, model: str, url_idx: Optional[int] = None):
    if url_idx is None:
        models = request.app.state.OLLAMA_MODELS
        if model not in models:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(model),
            )
        
        # Get candidate URLs for this model
        candidate_urls = models[model].get("urls", [])
        
        if not candidate_urls:
            raise HTTPException(
                status_code=400,
                detail=ERROR_MESSAGES.MODEL_NOT_FOUND(model),
            )
        
        # Implement weighted load balancing (active jobs + response time)
        min_score = float('inf')
        best_url_idx = None
        
        # Collect metrics for all candidates first (for normalization)
        server_metrics = []
        for idx in candidate_urls:
            url = request.app.state.config.OLLAMA_BASE_URLS[idx]
            
            # Extract base URL for load tracking
            try:
                parsed_url = urlparse(url)
                base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
            except Exception:
                base_url = url
            
            # Get current active jobs
            current_load = 0
            if hasattr(request.app.state, "redis") and request.app.state.redis:
                try:
                    key = f"active_jobs:{base_url}"
                    count = await request.app.state.redis.get(key)
                    current_load = int(count) if count else 0
                except Exception as e:
                    log.debug(f"Redis error reading job count for load balancing: {e}")
                    current_load = ACTIVE_JOB_STATS.get(base_url, 0)
            else:
                current_load = ACTIVE_JOB_STATS.get(base_url, 0)
            
            # Get average response time
            avg_response_time = 0.0
            if hasattr(request.app.state, "redis") and request.app.state.redis:
                try:
                    key = f"perf_avg_response_time:{base_url}"
                    avg_time = await request.app.state.redis.get(key)
                    avg_response_time = float(avg_time) if avg_time else 0.0
                except Exception as e:
                    log.debug(f"Redis error reading response time for load balancing: {e}")
                    avg_response_time = PERFORMANCE_STATS.get(base_url, {}).get("avg_response_time", 0.0)
            else:
                avg_response_time = PERFORMANCE_STATS.get(base_url, {}).get("avg_response_time", 0.0)
            
            # Check health status
            health_status = await get_health_status(base_url, request)
            
            server_metrics.append({
                "idx": idx,
                "base_url": base_url,
                "active_jobs": current_load,
                "avg_response_time": avg_response_time,
                "health_status": health_status
            })
        
        # Filter out unhealthy servers
        healthy_metrics = [m for m in server_metrics if m["health_status"] != "unhealthy"]
        
        # If all servers are unhealthy, use all servers (fallback)
        if not healthy_metrics:
            log.warning("All servers marked unhealthy, using all servers as fallback")
            healthy_metrics = server_metrics
        
        # Calculate weighted score for each healthy server
        # Lower score is better
        for metrics in healthy_metrics:
            # Use configurable weights from environment
            active_jobs_weight = OLLAMA_LB_ACTIVE_JOBS_WEIGHT
            response_time_weight = OLLAMA_LB_RESPONSE_TIME_WEIGHT
            
            # Score calculation
            # Active jobs: direct count (lower is better)
            # Response time: in milliseconds (lower is better)
            score = (
                active_jobs_weight * metrics["active_jobs"] +
                response_time_weight * (metrics["avg_response_time"] / 1000.0)  # Convert ms to seconds for balance
            )
            
            if score < min_score:
                min_score = score
                best_url_idx = metrics["idx"]
        
        # Use best server, fallback to random if none found
        url_idx = best_url_idx if best_url_idx is not None else random.choice(candidate_urls)
        
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
    return url, url_idx


@router.post("/api/chat")
@router.post("/api/chat/{url_idx}")
async def generate_chat_completion(
    request: Request,
    form_data: dict,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
    bypass_filter: Optional[bool] = False,
    bypass_system_prompt: bool = False,
    db: Session = Depends(get_session),
):
    if BYPASS_MODEL_ACCESS_CONTROL:
        bypass_filter = True

    metadata = form_data.pop("metadata", None)
    try:
        form_data = GenerateChatCompletionForm(**form_data)
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    if isinstance(form_data, BaseModel):
        payload = {**form_data.model_dump(exclude_none=True)}

    if "metadata" in payload:
        del payload["metadata"]

    model_id = payload["model"]
    model_info = Models.get_model_by_id(model_id, db=db)

    if model_info:
        if model_info.base_model_id:
            base_model_id = (
                request.base_model_id
                if hasattr(request, "base_model_id")
                else model_info.base_model_id
            )  # Use request's base_model_id if available
            payload["model"] = base_model_id

        params = model_info.params.model_dump()

        if params:
            system = params.pop("system", None)

            payload = apply_model_params_to_body_ollama(params, payload)
            if not bypass_system_prompt:
                payload = apply_system_prompt_to_body(system, payload, metadata, user)

        # Check if user has access to the model
        if not bypass_filter and user.role == "user":
            if not (
                user.id == model_info.user_id
                or has_access(
                    user.id,
                    type="read",
                    access_control=model_info.access_control,
                    db=db,
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Model not found",
                )
    elif not bypass_filter:
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Model not found",
            )

    if ":" not in payload["model"]:
        payload["model"] = f"{payload['model']}:latest"

    url, url_idx = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/api/chat",
        payload=json.dumps(payload),
        stream=form_data.stream,
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        content_type="application/x-ndjson",
        user=user,
        metadata=metadata,
        request=request,
    )


# TODO: we should update this part once Ollama supports other types
class OpenAIChatMessageContent(BaseModel):
    type: str
    model_config = ConfigDict(extra="allow")


class OpenAIChatMessage(BaseModel):
    role: str
    content: Union[Optional[str], list[OpenAIChatMessageContent]]

    model_config = ConfigDict(extra="allow")


class OpenAIChatCompletionForm(BaseModel):
    model: str
    messages: list[OpenAIChatMessage]

    model_config = ConfigDict(extra="allow")


class OpenAICompletionForm(BaseModel):
    model: str
    prompt: str

    model_config = ConfigDict(extra="allow")


@router.post("/v1/completions")
@router.post("/v1/completions/{url_idx}")
async def generate_openai_completion(
    request: Request,
    form_data: dict,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    metadata = form_data.pop("metadata", None)

    try:
        form_data = OpenAICompletionForm(**form_data)
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    payload = {**form_data.model_dump(exclude_none=True, exclude=["metadata"])}
    if "metadata" in payload:
        del payload["metadata"]

    model_id = form_data.model
    if ":" not in model_id:
        model_id = f"{model_id}:latest"

    model_info = Models.get_model_by_id(model_id, db=db)
    if model_info:
        if model_info.base_model_id:
            payload["model"] = model_info.base_model_id
        params = model_info.params.model_dump()

        if params:
            payload = apply_model_params_to_body_openai(params, payload)

        # Check if user has access to the model
        if user.role == "user":
            if not (
                user.id == model_info.user_id
                or has_access(
                    user.id,
                    type="read",
                    access_control=model_info.access_control,
                    db=db,
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Model not found",
                )
    else:
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Model not found",
            )

    if ":" not in payload["model"]:
        payload["model"] = f"{payload['model']}:latest"

    url, url_idx = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)

    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/v1/completions",
        payload=json.dumps(payload),
        stream=payload.get("stream", False),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
        metadata=metadata,
        request=request,
    )


@router.post("/v1/chat/completions")
@router.post("/v1/chat/completions/{url_idx}")
async def generate_openai_chat_completion(
    request: Request,
    form_data: dict,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    metadata = form_data.pop("metadata", None)

    try:
        completion_form = OpenAIChatCompletionForm(**form_data)
    except Exception as e:
        log.exception(e)
        raise HTTPException(
            status_code=400,
            detail=str(e),
        )

    payload = {**completion_form.model_dump(exclude_none=True, exclude=["metadata"])}
    if "metadata" in payload:
        del payload["metadata"]

    model_id = completion_form.model
    if ":" not in model_id:
        model_id = f"{model_id}:latest"

    model_info = Models.get_model_by_id(model_id, db=db)
    if model_info:
        if model_info.base_model_id:
            payload["model"] = model_info.base_model_id

        params = model_info.params.model_dump()

        if params:
            system = params.pop("system", None)

            payload = apply_model_params_to_body_openai(params, payload)
            payload = apply_system_prompt_to_body(system, payload, metadata, user)

        # Check if user has access to the model
        if user.role == "user":
            if not (
                user.id == model_info.user_id
                or has_access(
                    user.id,
                    type="read",
                    access_control=model_info.access_control,
                    db=db,
                )
            ):
                raise HTTPException(
                    status_code=403,
                    detail="Model not found",
                )
    else:
        if user.role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Model not found",
            )

    if ":" not in payload["model"]:
        payload["model"] = f"{payload['model']}:latest"

    url, url_idx = await get_ollama_url(request, payload["model"], url_idx)
    api_config = request.app.state.config.OLLAMA_API_CONFIGS.get(
        str(url_idx),
        request.app.state.config.OLLAMA_API_CONFIGS.get(url, {}),  # Legacy support
    )

    prefix_id = api_config.get("prefix_id", None)
    if prefix_id:
        payload["model"] = payload["model"].replace(f"{prefix_id}.", "")

    return await send_post_request(
        url=f"{url}/v1/chat/completions",
        payload=json.dumps(payload),
        stream=payload.get("stream", False),
        key=get_api_key(url_idx, url, request.app.state.config.OLLAMA_API_CONFIGS),
        user=user,
        metadata=metadata,
        request=request,
    )


@router.get("/v1/models")
@router.get("/v1/models/{url_idx}")
async def get_openai_models(
    request: Request,
    url_idx: Optional[int] = None,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):

    models = []
    if url_idx is None:
        model_list = await get_all_models(request, user=user)
        models = [
            {
                "id": model["model"],
                "object": "model",
                "created": int(time.time()),
                "owned_by": "openai",
            }
            for model in model_list["models"]
        ]

    else:
        url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]
        try:
            r = requests.request(method="GET", url=f"{url}/api/tags")
            r.raise_for_status()

            model_list = r.json()

            models = [
                {
                    "id": model["model"],
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "openai",
                }
                for model in models["models"]
            ]
        except Exception as e:
            log.exception(e)
            error_detail = "Open WebUI: Server Connection Error"
            if r is not None:
                try:
                    res = r.json()
                    if "error" in res:
                        error_detail = f"Ollama: {res['error']}"
                except Exception:
                    error_detail = f"Ollama: {e}"

            raise HTTPException(
                status_code=r.status_code if r else 500,
                detail=error_detail,
            )

    if user.role == "user" and not BYPASS_MODEL_ACCESS_CONTROL:
        # Filter models based on user access control
        filtered_models = []
        for model in models:
            model_info = Models.get_model_by_id(model["id"], db=db)
            if model_info:
                if user.id == model_info.user_id or has_access(
                    user.id,
                    type="read",
                    access_control=model_info.access_control,
                    db=db,
                ):
                    filtered_models.append(model)
        models = filtered_models

    return {
        "data": models,
        "object": "list",
    }


class UrlForm(BaseModel):
    url: str


class UploadBlobForm(BaseModel):
    filename: str


def parse_huggingface_url(hf_url):
    try:
        # Parse the URL
        parsed_url = urlparse(hf_url)

        # Get the path and split it into components
        path_components = parsed_url.path.split("/")

        # Extract the desired output
        model_file = path_components[-1]

        return model_file
    except ValueError:
        return None


async def download_file_stream(
    ollama_url, file_url, file_path, file_name, chunk_size=1024 * 1024
):
    done = False

    if os.path.exists(file_path):
        current_size = os.path.getsize(file_path)
    else:
        current_size = 0

    headers = {"Range": f"bytes={current_size}-"} if current_size > 0 else {}

    timeout = aiohttp.ClientTimeout(total=600)  # Set the timeout

    async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
        async with session.get(
            file_url, headers=headers, ssl=AIOHTTP_CLIENT_SESSION_SSL
        ) as response:
            total_size = int(response.headers.get("content-length", 0)) + current_size

            with open(file_path, "ab+") as file:
                async for data in response.content.iter_chunked(chunk_size):
                    current_size += len(data)
                    file.write(data)

                    done = current_size == total_size
                    progress = round((current_size / total_size) * 100, 2)

                    yield f'data: {{"progress": {progress}, "completed": {current_size}, "total": {total_size}}}\n\n'

                if done:
                    file.close()
                    hashed = calculate_sha256(file_path, chunk_size)

                    with open(file_path, "rb") as file:
                        chunk_size = 1024 * 1024 * 2
                        url = f"{ollama_url}/api/blobs/sha256:{hashed}"
                        with requests.Session() as session:
                            response = session.post(url, data=file, timeout=30)

                            if response.ok:
                                res = {
                                    "done": done,
                                    "blob": f"sha256:{hashed}",
                                    "name": file_name,
                                }
                                os.remove(file_path)

                                yield f"data: {json.dumps(res)}\n\n"
                            else:
                                raise "Ollama: Could not create blob, Please try again."


# url = "https://huggingface.co/TheBloke/stablelm-zephyr-3b-GGUF/resolve/main/stablelm-zephyr-3b.Q2_K.gguf"
@router.post("/models/download")
@router.post("/models/download/{url_idx}")
async def download_model(
    request: Request,
    form_data: UrlForm,
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    allowed_hosts = ["https://huggingface.co/", "https://github.com/"]

    if not any(form_data.url.startswith(host) for host in allowed_hosts):
        raise HTTPException(
            status_code=400,
            detail="Invalid file_url. Only URLs from allowed hosts are permitted.",
        )

    if url_idx is None:
        url_idx = 0
    url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

    file_name = parse_huggingface_url(form_data.url)

    if file_name:
        file_path = f"{UPLOAD_DIR}/{file_name}"

        return StreamingResponse(
            download_file_stream(url, form_data.url, file_path, file_name),
        )
    else:
        return None


# TODO: Progress bar does not reflect size & duration of upload.
@router.post("/models/upload")
@router.post("/models/upload/{url_idx}")
async def upload_model(
    request: Request,
    file: UploadFile = File(...),
    url_idx: Optional[int] = None,
    user=Depends(get_admin_user),
):
    if url_idx is None:
        url_idx = 0
    ollama_url = request.app.state.config.OLLAMA_BASE_URLS[url_idx]

    filename = os.path.basename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)

    # --- P1: save file locally ---
    chunk_size = 1024 * 1024 * 2  # 2 MB chunks
    with open(file_path, "wb") as out_f:
        while True:
            chunk = file.file.read(chunk_size)
            # log.info(f"Chunk: {str(chunk)}") # DEBUG
            if not chunk:
                break
            out_f.write(chunk)

    async def file_process_stream():
        nonlocal ollama_url
        total_size = os.path.getsize(file_path)
        log.info(f"Total Model Size: {str(total_size)}")  # DEBUG

        # --- P2: SSE progress + calculate sha256 hash ---
        file_hash = calculate_sha256(file_path, chunk_size)
        log.info(f"Model Hash: {str(file_hash)}")  # DEBUG
        try:
            with open(file_path, "rb") as f:
                bytes_read = 0
                while chunk := f.read(chunk_size):
                    bytes_read += len(chunk)
                    progress = round(bytes_read / total_size * 100, 2)
                    data_msg = {
                        "progress": progress,
                        "total": total_size,
                        "completed": bytes_read,
                    }
                    yield f"data: {json.dumps(data_msg)}\n\n"

            # --- P3: Upload to ollama /api/blobs ---
            with open(file_path, "rb") as f:
                url = f"{ollama_url}/api/blobs/sha256:{file_hash}"
                response = requests.post(url, data=f)

            if response.ok:
                log.info(f"Uploaded to /api/blobs")  # DEBUG
                # Remove local file
                os.remove(file_path)

                # Create model in ollama
                model_name, ext = os.path.splitext(filename)
                log.info(f"Created Model: {model_name}")  # DEBUG

                create_payload = {
                    "model": model_name,
                    # Reference the file by its original name => the uploaded blob's digest
                    "files": {filename: f"sha256:{file_hash}"},
                }
                log.info(f"Model Payload: {create_payload}")  # DEBUG

                # Call ollama /api/create
                # https://github.com/ollama/ollama/blob/main/docs/api.md#create-a-model
                create_resp = requests.post(
                    url=f"{ollama_url}/api/create",
                    headers={"Content-Type": "application/json"},
                    data=json.dumps(create_payload),
                )

                if create_resp.ok:
                    log.info(f"API SUCCESS!")  # DEBUG
                    done_msg = {
                        "done": True,
                        "blob": f"sha256:{file_hash}",
                        "name": filename,
                        "model_created": model_name,
                    }
                    yield f"data: {json.dumps(done_msg)}\n\n"
                else:
                    raise Exception(
                        f"Failed to create model in Ollama. {create_resp.text}"
                    )

            else:
                raise Exception("Ollama: Could not create blob, Please try again.")

        except Exception as e:
            res = {"error": str(e)}
            yield f"data: {json.dumps(res)}\n\n"

    return StreamingResponse(file_process_stream(), media_type="text/event-stream")
