# Job Queue & System API Reference

All endpoints require a bearer token in the `Authorization` header:
```
Authorization: Bearer <your-token>
```

Base URL: `http://localhost:8080/api/v1`

---

## Table of Contents

| Group | Endpoints |
|-------|-----------|
| [Jobs — Submit & Poll](#jobs--submit--poll) | `POST /jobs/chat/completions`, `GET /jobs/{id}`, `DELETE /jobs/{id}` |
| [Jobs — List & Filter](#jobs--list--filter) | `GET /jobs/`, `GET /jobs/admin/list` |
| [Jobs — Retry](#jobs--retry) | `POST /jobs/{id}/retry` |
| [Jobs — SSE Notifications](#jobs--sse-notifications) | `GET /jobs/events` |
| [Jobs — Archive](#jobs--archive) | `GET /jobs/archive`, `GET /jobs/archive/config`, `POST /jobs/archive/run` |
| [Jobs — Analytics](#jobs--analytics) | `GET /jobs/analytics`, `GET /jobs/analytics/export` |
| [System — Metrics](#system--metrics) | `GET /system/metrics` |
| [System — LB Strategy](#system--lb-strategy) | `GET /system/lb-strategy`, `POST /system/lb-strategy` |
| [System — Backend Snapshots](#system--backend-snapshots) | `GET /system/snapshots` |

---

## Jobs — Submit & Poll

### `POST /jobs/chat/completions`

Submit an async chat-completion job. Returns **202 Accepted** immediately.
The job is queued and executed by the background scheduler.

**Auth:** Any verified user.

**Request Body**
```json
{
  "model": "llama3",
  "messages": [
    { "role": "user", "content": "Summarise the history of Rome in 3 sentences." }
  ],
  "temperature": 0.7,
  "max_tokens": 512
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `model` | string | ✅ | Model ID (must exist in `MODELS`) |
| `messages` | array | ✅ | OpenAI-format message array |
| `temperature` | float | — | Sampling temperature (0–2) |
| `max_tokens` | int | — | Maximum tokens in response |
| `stream` | boolean | — | Ignored — always forced to `false` |

**Response — 202**
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "queued",
  "model_id": "llama3",
  "created_at": 1740170000
}
```

**Errors**
| Code | Reason |
|------|--------|
| 404 | Model not found |
| 500 | DB job creation failed |

**cURL**
```bash
curl -X POST http://localhost:8080/api/v1/jobs/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "llama3",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

---

### `GET /jobs/{job_id}`

Poll the status of a job. Result is cached in Redis (TTL 10 s) for terminal jobs.

**Auth:** Verified user (must own the job).

**Query Parameters**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `include_result` | bool | `true` | Set to `false` to skip result payload (saves bandwidth while polling) |

**Response — 200**
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "completed",
  "model_id": "llama3",
  "backend_url": "http://localhost:11434",
  "attempt_count": 1,
  "max_attempts": 3,
  "created_at": 1740170000,
  "updated_at": 1740170045,
  "result": {
    "id": "chatcmpl-abc",
    "choices": [{ "message": { "role": "assistant", "content": "Hi there!" } }]
  },
  "error": null
}
```

**Status values:** `queued` | `running` | `completed` | `failed` | `cancelled`

**Errors**
| Code | Reason |
|------|--------|
| 403 | Job belongs to a different user |
| 404 | Job not found |

**cURL — polling loop**
```bash
JOB_ID="3fa85f64-5717-4562-b3fc-2c963f66afa6"
while true; do
  STATUS=$(curl -s -H "Authorization: Bearer $TOKEN" \
    "http://localhost:8080/api/v1/jobs/$JOB_ID?include_result=false" | jq -r .status)
  echo "Status: $STATUS"
  [[ "$STATUS" == "completed" || "$STATUS" == "failed" ]] && break
  sleep 3
done

# Fetch full result
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/jobs/$JOB_ID" | jq .result
```

---

### `DELETE /jobs/{job_id}`

Cancel a queued or running job. If already terminal, returns the current state without error.

**Auth:** Verified user (must own the job).

**Response — 200** — Same schema as `GET /{job_id}` with `status: "cancelled"`.

**Errors**
| Code | Reason |
|------|--------|
| 403 | Not the job owner |
| 404 | Job not found |

**cURL**
```bash
curl -X DELETE http://localhost:8080/api/v1/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN"
```

---

## Jobs — List & Filter

### `GET /jobs/`

List the authenticated user's own jobs, newest first.

**Auth:** Any verified user.

**Query Parameters**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `skip` | int | `0` | Pagination offset |
| `limit` | int | `50` | Max results (1–200) |
| `status` | string | — | Filter: `queued` \| `running` \| `completed` \| `failed` \| `cancelled` |
| `model_id` | string | — | Filter by model ID (e.g. `llama3`) |

**Response — 200**
```json
{
  "jobs": [ /* array of JobResponse objects */ ],
  "total": 42,
  "skip": 0,
  "limit": 50
}
```

**cURL**
```bash
# Own jobs — only failed ones
curl "http://localhost:8080/api/v1/jobs/?status=failed&limit=10" \
  -H "Authorization: Bearer $TOKEN"
```

---

### `GET /jobs/admin/list`

Admin view of **all** users' jobs, with optional filters.

**Auth:** Admin only.

**Query Parameters**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `skip` | int | `0` | Pagination offset |
| `limit` | int | `50` | Max results (1–200) |
| `status` | string | — | Filter by job status |
| `model_id` | string | — | Filter by model |
| `user_id` | string | — | Filter by user UUID |

**Response — 200** — Same shape as `GET /jobs/`.

**cURL**
```bash
curl "http://localhost:8080/api/v1/jobs/admin/list?status=running&model_id=llama3" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Jobs — Retry

### `POST /jobs/{job_id}/retry`

Reset a terminal job (`failed` or `cancelled`) back to `queued` so the scheduler picks it up again.
Clears `error`, resets `attempt_count` to 0.

**Auth:** Admin only.

**Response — 200** — Updated `JobResponse` with `status: "queued"`.

**Errors**
| Code | Reason |
|------|--------|
| 404 | Job not found |
| 409 | Job is not in a terminal state |

**cURL**
```bash
curl -X POST http://localhost:8080/api/v1/jobs/$JOB_ID/retry \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Jobs — SSE Notifications

### `GET /jobs/events`

**Server-Sent Events** stream. Connect once after login and receive real-time push events whenever one of your jobs changes state (completed or failed).

**Auth:** Any verified user.

**Event format**
```
data: {"job_id": "...", "status": "completed", "updated_at": 1740170045}

data: {"job_id": "...", "status": "failed", "error": "timeout", "updated_at": 1740170060}
```

Heartbeat (ignore):
```
data: {"ping": true}
```

Keepalive comment every 30 s:
```
: keepalive
```

**Notes**
- The connection stays open until the browser disconnects.
- Use the `initJobEvents(token)` helper from `src/lib/stores/jobEvents.ts` in the frontend.

**cURL**
```bash
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/v1/jobs/events
```

**JavaScript (EventSource)**
```js
import { initJobEvents, latestJobEvent } from '$lib/stores/jobEvents';

// Call once after login
initJobEvents(token, (event) => {
  if (event.status === 'completed') {
    console.log(`Job ${event.job_id} finished!`);
  }
});

// OR subscribe to the writable store
latestJobEvent.subscribe((e) => e && console.log(e));
```

---

## Jobs — Archive

### `GET /jobs/archive`

Browse jobs that have been moved to the archive table (older than `JOB_RETENTION_DAYS`).

**Auth:** Admin only.

**Query Parameters**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `skip` | int | `0` | Pagination offset |
| `limit` | int | `50` | Max results (1–200) |
| `status` | string | — | Filter by status |
| `model_id` | string | — | Filter by model |

**Response — 200** — Same shape as `GET /jobs/`.

---

### `GET /jobs/archive/config`

Return the active retention policy from env vars.

**Auth:** Admin only.

**Response — 200**
```json
{
  "job_retention_days": 30,
  "job_archive_retention_days": 365,
  "note": "Set JOB_RETENTION_DAYS / JOB_ARCHIVE_RETENTION_DAYS env vars to override."
}
```

**Environment variables**

| Variable | Default | Description |
|----------|---------|-------------|
| `JOB_RETENTION_DAYS` | `30` | Days before a terminal job moves to `job_archive` |
| `JOB_ARCHIVE_RETENTION_DAYS` | `365` | Days before an archived row is hard-deleted. Set to `0` to disable purging. |

---

### `POST /jobs/archive/run`

Manually trigger an archive sweep + purge without waiting for the hourly scheduler.

**Auth:** Admin only.

**Response — 200**
```json
{
  "archived": 12,
  "purged": 3,
  "job_retention_days": 30,
  "job_archive_retention_days": 365
}
```

---

## Jobs — Analytics

### `GET /jobs/analytics`

Aggregate statistics across active (and optionally archived) jobs.

**Auth:** Admin only.

**Query Parameters**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `combined` | bool | `true` | Include `job_archive` rows for all-time history |

**Response — 200**
```json
{
  "total": 1500,
  "includes_archive": true,
  "success_rate": 94.3,
  "avg_wait_seconds": 8,
  "by_status": {
    "completed": 1413,
    "failed": 62,
    "cancelled": 12,
    "queued": 8,
    "running": 5
  },
  "by_model": [
    { "model_id": "llama3", "total": 900, "completed": 855, "failed": 30, "cancelled": 15 }
  ],
  "by_user": [
    {
      "user_id": "uuid-...",
      "name": "Alice Smith",
      "email": "alice@example.com",
      "total": 320,
      "completed": 310,
      "failed": 8,
      "cancelled": 2
    }
  ],
  "daily_history": [
    { "date": "2026-02-01", "total": 42, "completed": 40, "failed": 2 },
    { "date": "2026-02-02", "total": 55, "completed": 53, "failed": 2 }
  ]
}
```

> `daily_history` covers the last **90 days**. Works on both SQLite and PostgreSQL.

---

### `GET /jobs/analytics/export`

Download analytics as a CSV file containing `daily_history` and `by_model` sections.

**Auth:** Admin only.

**Response** — `Content-Type: text/csv; Content-Disposition: attachment; filename=job_analytics.csv`

```csv
section,date,total,completed,failed
daily,2026-02-01,42,40,2
daily,2026-02-02,55,53,2

section,model_id,total,completed,failed
model,llama3,900,855,30
model,phi3,600,558,32
```

**cURL**
```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8080/api/v1/jobs/analytics/export" \
  -o job_analytics.csv
```

---

## System — Metrics

### `GET /system/metrics`

Real-time server resource usage + per-Ollama-backend `/api/ps` data.

**Auth:** Admin only.

**Response — 200**
```json
{
  "server": {
    "cpu_percent": 14.2,
    "ram_total_gb": 32.0,
    "ram_used_gb": 18.4,
    "ram_percent": 57.5,
    "disk_total_gb": 500.0,
    "disk_used_gb": 210.3,
    "disk_percent": 42.1
  },
  "ollama_backends": {
    "http://localhost:11434": {
      "api_ps": {
        "models": [
          {
            "name": "llama3:latest",
            "model": "llama3:latest",
            "size": 4661211136,
            "size_vram": 4661211136,
            "expires_at": "2026-02-21T20:00:00Z"
          }
        ]
      }
    }
  }
}
```

---

## System — LB Strategy

### `GET /system/lb-strategy`

Get the current Ollama load-balancing algorithm.

**Auth:** Admin only.

**Response — 200**
```json
{
  "strategy": "least_connections",
  "available": ["fastest", "least_connections", "round_robin"],
  "source": "redis"
}
```

| Strategy | Behaviour |
|----------|-----------|
| `least_connections` | Route to the backend with fewest active jobs (default) |
| `round_robin` | Cycle through backends in order |
| `fastest` | Route to the backend with lowest average response time |

---

### `POST /system/lb-strategy`

Change the active load-balancing algorithm. Takes effect immediately. Persisted to Redis; env var `OLLAMA_LB_STRATEGY` is updated in-process as a fallback.

**Auth:** Admin only.

**Request Body**
```json
{ "strategy": "round_robin" }
```

**Response — 200**
```json
{ "strategy": "round_robin", "saved": true }
```

**Errors**
| Code | Reason |
|------|--------|
| 422 | Invalid strategy value |

**cURL**
```bash
curl -X POST http://localhost:8080/api/v1/system/lb-strategy \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"strategy": "round_robin"}'
```

**Environment variable**

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_LB_STRATEGY` | `least_connections` | Default strategy when Redis is unavailable |

---

## System — Backend Snapshots

### `GET /system/snapshots`

Time-series backend metric data, grouped by backend URL. Each snapshot is one data point collected every `BACKEND_SNAPSHOT_INTERVAL` seconds (default: 5 min).

**Auth:** Admin only.

**Query Parameters**

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | `60` | Max snapshots per backend (1–500) |
| `since` | int | — | Only return snapshots after this Unix epoch second |
| `backend_url` | string | — | Filter to a single backend URL |

**Response — 200**
```json
{
  "backends": {
    "http://localhost:11434": [
      {
        "id": 1,
        "captured_at": 1740170000,
        "backend_url": "http://localhost:11434",
        "cpu_percent": 14.2,
        "ram_percent": 57.5,
        "active_jobs": 3,
        "queued_jobs": 7,
        "loaded_models": 2,
        "vram_used_gb": 8.64,
        "avg_tokens_per_second": null
      }
    ]
  },
  "count": 72
}
```

> Snapshots older than `BACKEND_SNAPSHOT_RETENTION_DAYS` (default 7) are automatically purged daily.

**cURL — get last hour of data**
```bash
SINCE=$(date -v-1H +%s)   # macOS
# SINCE=$(date -d '1 hour ago' +%s)  # Linux

curl "http://localhost:8080/api/v1/system/snapshots?since=$SINCE&limit=500" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

**Environment variables**

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_SNAPSHOT_INTERVAL` | `300` | Seconds between snapshots |
| `BACKEND_SNAPSHOT_RETENTION_DAYS` | `7` | Days to keep snapshots before purging |

---

## Job Status Reference

| Status | Terminal? | Description |
|--------|-----------|-------------|
| `queued` | ❌ | Waiting to be picked up by the scheduler |
| `running` | ❌ | Actively executing |
| `completed` | ✅ | Finished successfully — `result` is populated |
| `failed` | ✅ | Errored — `error` contains the message. May be re-queued if `attempt_count < max_attempts` |
| `cancelled` | ✅ | Cancelled by the user or admin |

## DB Schema Overview

```
job                         job_archive                 backend_snapshot
─────────────────────────   ─────────────────────────   ─────────────────────────────
id (uuid)                   id (uuid)                   id (int, auto)
user_id                     user_id                     captured_at (epoch)
model_id                    model_id                    backend_url
status                      status                      cpu_percent
priority                    priority                    ram_percent
priority_score              priority_score              active_jobs
backend_url                 backend_url                 queued_jobs
request (json)              request (json)              loaded_models
result  (json)              result  (json)              vram_used_gb
error                       error                       avg_tokens_per_second
attempt_count               attempt_count
max_attempts                max_attempts
created_at                  created_at
updated_at                  updated_at
                            archived_at
```
