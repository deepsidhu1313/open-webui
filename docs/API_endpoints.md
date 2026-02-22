# Open WebUI — Complete API Reference

> **Base URL:** `http://<host>:8080`
> **Auth:** All protected endpoints require `Authorization: Bearer <token>` (user JWT or API key).
>
> | Symbol | Meaning |
> |--------|---------|
> | 🌐 | Public — no auth |
> | ✅ | Any verified user |
> | 🔒 | Admin only |

---

## Table of Contents

1. [Authentication](#1-authentication)
2. [Users](#2-users)
3. [Chats](#3-chats)
4. [Channels](#4-channels)
5. [Notes](#5-notes)
6. [Models](#6-models)
7. [Knowledge](#7-knowledge)
8. [Prompts](#8-prompts)
9. [Tools](#9-tools)
10. [Skills](#10-skills)
11. [Functions](#11-functions)
12. [Memories](#12-memories)
13. [Folders](#13-folders)
14. [Groups](#14-groups)
15. [Files](#15-files)
16. [Images](#16-images)
17. [Audio](#17-audio)
18. [Retrieval / RAG](#18-retrieval--rag)
19. [Pipelines](#19-pipelines)
20. [Tasks](#20-tasks)
21. [Configs](#21-configs)
22. [Evaluations](#22-evaluations)
23. [Analytics](#23-analytics)
24. [Jobs ⭐](#24-jobs-)
25. [System ⭐](#25-system-)
26. [Utils](#26-utils)
27. [SCIM](#27-scim)
28. [Ollama Proxy](#28-ollama-proxy)
29. [OpenAI Proxy](#29-openai-proxy)

---

## 1. Authentication

Base: `/api/v1/auths`

### Quick Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | Session info |
| POST | `/signin` | 🌐 | Sign in |
| POST | `/signup` | 🌐 | Register |
| POST | `/signout` | ✅ | Sign out |
| POST | `/add` | 🔒 | Create user |
| POST | `/password/update` | ✅ | Change password |
| POST | `/api_key` | ✅ | Regenerate API key |
| GET | `/api_key` | ✅ | Get API key |
| DELETE | `/api_key` | ✅ | Delete API key |
| GET | `/config` | 🔒 | Auth config |
| POST | `/config/update` | 🔒 | Update auth config |
| GET | `/oauth/providers` | 🌐 | Enabled OAuth providers |
| GET | `/oauth/{provider}/login` | 🌐 | Start OAuth flow |
| GET | `/ldap/config` | 🔒 | LDAP config |
| POST | `/ldap/config/update` | 🔒 | Update LDAP config |
| POST | `/ldap/signin` | 🌐 | LDAP sign in |

---

### `POST /api/v1/auths/signin` 🌐

Sign in with email and password, or API key.

**Request**
```json
{ "email": "user@example.com", "password": "s3cret" }
```
**Response — 200**
```json
{
  "token": "eyJhbGciOiJIUzI1NiJ9...",
  "token_type": "Bearer",
  "id": "uuid-...",
  "email": "user@example.com",
  "name": "Alice",
  "role": "user",
  "profile_image_url": "/user.png"
}
```
**Errors:** `400` — wrong credentials
```bash
curl -X POST http://localhost:8080/api/v1/auths/signin \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"s3cret"}'
```

---

### `POST /api/v1/auths/signup` 🌐

Register a new account (only when sign-up is enabled).

**Request**
```json
{ "name": "Alice", "email": "alice@example.com", "password": "s3cret" }
```
**Response — 200** — same as `/signin`

**Errors:** `400` — email already registered, sign-up disabled

---

### `POST /api/v1/auths/add` 🔒

Admin-created user account.

**Request**
```json
{ "name": "Bob", "email": "bob@example.com", "password": "temp123", "role": "user" }
```
**Response — 200** — user object

---

### `POST /api/v1/auths/password/update` ✅

Change own password.

**Request**
```json
{ "password": "old_pass", "new_password": "new_pass" }
```
**Response — 200** — `{ "message": "Password updated successfully" }`

---

## 2. Users

Base: `/api/v1/users`

### Quick Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | 🔒 | List users (paginated) |
| GET | `/all` | 🔒 | All users |
| GET | `/search` | 🔒 | Search by name/email |
| GET | `/permissions` | ✅ | Own permissions |
| GET | `/default/permissions` | 🔒 | Default permissions |
| POST | `/default/permissions` | 🔒 | Update defaults |
| GET | `/user/settings` | ✅ | Own UI settings |
| POST | `/user/settings/update` | ✅ | Update UI settings |
| GET | `/{user_id}` | 🔒 | Get user |
| POST | `/{user_id}/update` | 🔒 | Update user |
| DELETE | `/{user_id}` | 🔒 | Delete user |
| GET | `/{user_id}/groups` | 🔒 | User's groups |
| PATCH | `/{user_id}/job-priority` | 🔒 | Set job queue priority |

---

### `GET /api/v1/users/` 🔒

```
GET /api/v1/users/?skip=0&limit=20&sort_by=created_at
```
**Response**
```json
[
  { "id": "uuid", "name": "Alice", "email": "alice@example.com", "role": "user", "active": true, "created_at": 1740000000 }
]
```

---

### `GET /api/v1/users/search` 🔒

```
GET /api/v1/users/search?q=alice&skip=0&limit=20
```

---

### `POST /api/v1/users/{user_id}/update` 🔒

**Request**
```json
{ "name": "Alice Smith", "email": "alice@example.com", "role": "admin", "active": true }
```

---

### `PATCH /api/v1/users/{user_id}/job-priority` 🔒

Set per-user job queue priority (1 = lowest, 10 = highest).

**Request**
```json
{ "priority": 8 }
```
**Response — 200**
```json
{ "id": "uuid", "job_priority": 8 }
```
```bash
curl -X PATCH http://localhost:8080/api/v1/users/$USER_ID/job-priority \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"priority": 8}'
```

---

## 3. Chats

Base: `/api/v1/chats`

### Quick Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List own chats (paginated) |
| POST | `/new` | ✅ | Create chat |
| GET | `/{id}` | ✅ | Get chat |
| DELETE | `/{id}` | ✅ | Delete chat |
| POST | `/{id}/archive` | ✅ | Archive |
| POST | `/{id}/pin` | ✅ | Pin / unpin |
| POST | `/{id}/share` | ✅ | Share |
| GET | `/{id}/messages` | ✅ | Get messages |
| POST | `/{id}/messages/post` | ✅ | Append message |
| GET | `/pinned` | ✅ | Pinned chats |
| GET | `/archived` | ✅ | Archived chats |
| GET | `/search` | ✅ | Full-text search |
| GET | `/export` | ✅ | Export all as JSON |
| POST | `/import` | ✅ | Import JSON |
| DELETE | `/` | ✅ | Delete all own chats |

---

### `POST /api/v1/chats/new` ✅

**Request**
```json
{
  "chat": {
    "title": "My Chat",
    "models": ["llama3"],
    "messages": [
      { "id": "msg-1", "parentId": null, "childrenIds": [], "role": "user", "content": "Hello" }
    ]
  }
}
```
**Response — 200**
```json
{
  "id": "chat-uuid",
  "title": "My Chat",
  "models": ["llama3"],
  "created_at": 1740170000,
  "updated_at": 1740170000,
  "share_id": null,
  "archived": false,
  "pinned": false
}
```

---

### `GET /api/v1/chats/search` ✅

```
GET /api/v1/chats/search?q=rome&skip=0&limit=20
```

---

## 4. Channels

Base: `/api/v1/channels`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List channels |
| POST | `/create` | 🔒 | Create channel |
| GET | `/{id}` | ✅ | Get channel |
| POST | `/{id}/update` | 🔒 | Update channel |
| DELETE | `/{id}/delete` | 🔒 | Delete channel |
| GET | `/{id}/messages` | ✅ | Get messages |
| POST | `/{id}/messages/post` | ✅ | Post message |
| POST | `/{id}/messages/{msg_id}/update` | ✅ | Edit message |
| DELETE | `/{id}/messages/{msg_id}/delete` | ✅ | Delete message |
| POST | `/{id}/messages/{msg_id}/reactions` | ✅ | Add reaction |
| DELETE | `/{id}/messages/{msg_id}/reactions` | ✅ | Remove reaction |

---

### `POST /api/v1/channels/create` 🔒

**Request**
```json
{ "name": "general", "description": "General discussion", "access_control": null }
```

### `POST /api/v1/channels/{id}/messages/post` ✅

**Request**
```json
{ "content": "Hello everyone!", "parent_id": null }
```

---

## 5. Notes

Base: `/api/v1/notes`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List notes |
| POST | `/create` | ✅ | Create note |
| GET | `/id/{id}` | ✅ | Get note |
| POST | `/id/{id}/update` | ✅ | Update note |
| DELETE | `/id/{id}/delete` | ✅ | Delete note |

### `POST /api/v1/notes/create` ✅

**Request**
```json
{ "title": "Meeting notes", "data": { "content": "## Agenda\n- Item 1" } }
```

---

## 6. Models

Base: `/api/v1/models`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | All available models (Ollama + OpenAI + custom) |
| GET | `/base` | 🔒 | Custom base models |
| POST | `/create` | 🔒 | Create custom model |
| GET | `/id/{id}` | ✅ | Get model |
| POST | `/id/{id}/update` | 🔒 | Update model |
| DELETE | `/id/{id}/delete` | 🔒 | Delete model |
| POST | `/id/{id}/access/update` | 🔒 | Set visibility |
| GET | `/id/{id}/toggle` | 🔒 | Enable / disable |

### `GET /api/v1/models/` ✅

**Response**
```json
{
  "data": [
    { "id": "llama3:latest", "name": "Llama 3", "owned_by": "ollama" },
    { "id": "gpt-4o", "name": "GPT-4o", "owned_by": "openai" }
  ]
}
```

---

## 7. Knowledge

Base: `/api/v1/knowledge`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List knowledge bases |
| POST | `/create` | ✅ | Create knowledge base |
| GET | `/{id}` | ✅ | Get with files |
| POST | `/{id}/update` | ✅ | Update metadata |
| DELETE | `/{id}/delete` | ✅ | Delete |
| POST | `/{id}/file/add` | ✅ | Add file to KB |
| POST | `/{id}/file/remove` | ✅ | Remove file |
| POST | `/{id}/files/batch/add` | ✅ | Add multiple files |
| POST | `/{id}/reset` | ✅ | Re-index |
| POST | `/{id}/access/update` | 🔒 | Set access |

### `POST /api/v1/knowledge/create` ✅

**Request**
```json
{ "name": "Product Docs", "description": "Internal product documentation", "data": {} }
```

### `POST /api/v1/knowledge/{id}/file/add` ✅

**Request**
```json
{ "file_id": "file-uuid" }
```

---

## 8. Prompts

Base: `/api/v1/prompts`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List prompts |
| POST | `/create` | ✅ | Create |
| GET | `/command/{command}` | ✅ | Lookup by slash command |
| GET | `/id/{id}` | ✅ | Get |
| POST | `/id/{id}/update` | ✅ | Update |
| DELETE | `/id/{id}/delete` | ✅ | Delete |
| GET | `/id/{id}/history` | ✅ | Version history |
| DELETE | `/id/{id}/history/{history_id}` | ✅ | Delete version |
| GET | `/id/{id}/history/diff` | ✅ | Diff versions |

### `POST /api/v1/prompts/create` ✅

**Request**
```json
{
  "command": "/summarize",
  "title": "Summarize Text",
  "content": "Summarize the following in 3 bullet points:\n\n{{input}}"
}
```

---

## 9. Tools

Base: `/api/v1/tools`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List tools |
| POST | `/create` | ✅ | Create tool |
| POST | `/load/url` | ✅ | Import from URL |
| GET | `/export` | 🔒 | Export all |
| GET | `/id/{id}` | ✅ | Get tool |
| POST | `/id/{id}/update` | ✅ | Update |
| DELETE | `/id/{id}/delete` | ✅ | Delete |
| GET | `/id/{id}/valves` | ✅ | Admin valves |
| GET | `/id/{id}/valves/spec` | ✅ | Valve JSON schema |
| POST | `/id/{id}/valves/update` | 🔒 | Update admin valves |
| GET | `/id/{id}/valves/user` | ✅ | User valves |
| POST | `/id/{id}/valves/user/update` | ✅ | Update user valves |

### `POST /api/v1/tools/create` ✅

**Request**
```json
{
  "id": "web_search",
  "name": "Web Search",
  "content": "# Tool code (Python)...",
  "meta": { "description": "Search the web", "author": "Alice" }
}
```

---

## 10. Skills

Base: `/api/v1/skills`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List skills |
| POST | `/create` | ✅ | Create |
| GET | `/id/{id}` | ✅ | Get |
| POST | `/id/{id}/update` | ✅ | Update |
| DELETE | `/id/{id}/delete` | ✅ | Delete |
| POST | `/id/{id}/toggle` | 🔒 | Enable / disable |
| POST | `/id/{id}/access/update` | 🔒 | Set access |
| GET | `/export` | 🔒 | Export all |

---

## 11. Functions

Base: `/api/v1/functions`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List functions |
| POST | `/create` | ✅ | Create |
| GET | `/id/{id}` | ✅ | Get |
| POST | `/id/{id}/update` | ✅ | Update |
| DELETE | `/id/{id}/delete` | ✅ | Delete |
| GET | `/id/{id}/toggle` | 🔒 | Enable / disable |
| GET | `/id/{id}/toggle/global` | 🔒 | Toggle global |
| GET | `/id/{id}/valves` | ✅ | Admin valves |
| POST | `/id/{id}/valves/update` | 🔒 | Update admin valves |
| GET | `/id/{id}/valves/user` | ✅ | User valves |
| POST | `/id/{id}/valves/user/update` | ✅ | Update user valves |
| GET | `/export` | 🔒 | Export all |

---

## 12. Memories

Base: `/api/v1/memories`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List own memories |
| POST | `/add` | ✅ | Add memory |
| POST | `/query` | ✅ | Semantic search |
| DELETE | `/` | ✅ | Delete all |
| POST | `/{id}/update` | ✅ | Update |
| DELETE | `/{id}` | ✅ | Delete one |

### `POST /api/v1/memories/add` ✅

**Request**
```json
{ "content": "Alice's preferred language is TypeScript." }
```
**Response**
```json
{ "id": "mem-uuid", "content": "Alice's preferred language is TypeScript.", "created_at": 1740170000 }
```

### `POST /api/v1/memories/query` ✅

**Request**
```json
{ "content": "programming preferences", "k": 5 }
```

---

## 13. Folders

Base: `/api/v1/folders`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List folders |
| POST | `/create` | ✅ | Create |
| GET | `/id/{id}` | ✅ | Get |
| POST | `/id/{id}/update` | ✅ | Rename |
| DELETE | `/id/{id}/delete` | ✅ | Delete |
| POST | `/id/{id}/chats` | ✅ | Add chat(s) |
| DELETE | `/id/{id}/chats/{chat_id}` | ✅ | Remove chat |

### `POST /api/v1/folders/create` ✅

**Request**
```json
{ "name": "Work Projects" }
```

---

## 14. Groups

Base: `/api/v1/groups`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | 🔒 | List groups |
| POST | `/create` | 🔒 | Create |
| GET | `/id/{id}` | 🔒 | Get |
| POST | `/id/{id}/update` | 🔒 | Update |
| DELETE | `/id/{id}/delete` | 🔒 | Delete |
| POST | `/id/{id}/users/add` | 🔒 | Add users |
| DELETE | `/id/{id}/users/delete` | 🔒 | Remove users |

### `POST /api/v1/groups/create` 🔒

**Request**
```json
{
  "name": "Data Team",
  "description": "Data science team",
  "user_ids": ["uuid-1", "uuid-2"],
  "permissions": { "workspace": { "models": true, "knowledge": true } }
}
```

---

## 15. Files

Base: `/api/v1/files`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/` | ✅ | Upload file |
| GET | `/` | ✅ | List own files |
| GET | `/{id}` | ✅ | File metadata |
| GET | `/{id}/content` | ✅ | Download content |
| GET | `/{id}/content/{file_name}` | ✅ | Download with name |
| POST | `/{id}/data/content/update` | ✅ | Update extracted text |
| DELETE | `/{id}` | ✅ | Delete |
| GET | `/config` | 🔒 | Storage config |
| POST | `/config/update` | 🔒 | Update config |

### `POST /api/v1/files/` ✅

Upload a file using `multipart/form-data`.

**Request**
```bash
curl -X POST http://localhost:8080/api/v1/files/ \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@report.pdf;type=application/pdf"
```
**Response — 200**
```json
{
  "id": "file-uuid",
  "filename": "report.pdf",
  "meta": { "name": "report.pdf", "content_type": "application/pdf", "size": 204800 },
  "created_at": 1740170000
}
```

---

## 16. Images

Base: `/api/v1/images`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/config` | 🔒 | Image gen config |
| POST | `/config/update` | 🔒 | Update config |
| GET | `/models` | ✅ | Available image models |
| POST | `/generations` | ✅ | Generate image |

### `POST /api/v1/images/generations` ✅

**Request**
```json
{
  "prompt": "A futuristic city at sunset, cyberpunk style",
  "model": "stable-diffusion",
  "n": 1,
  "size": "1024x1024"
}
```
**Response — 200**
```json
{
  "images": [
    { "url": "/cache/image/xyz.png" }
  ]
}
```

---

## 17. Audio

Base: `/api/v1/audio`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/config` | 🔒 | Audio config |
| POST | `/config/update` | 🔒 | Update config |
| POST | `/speech` | ✅ | Text → audio |
| POST | `/transcriptions` | ✅ | Audio → text |

### `POST /api/v1/audio/speech` ✅

**Request**
```json
{ "model": "tts-1", "input": "Hello, world!", "voice": "alloy" }
```
**Response** — `audio/mpeg` binary stream

```bash
curl -X POST http://localhost:8080/api/v1/audio/speech \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"tts-1","input":"Hello!","voice":"alloy"}' \
  --output hello.mp3
```

### `POST /api/v1/audio/transcriptions` ✅

**Request** — `multipart/form-data`
```bash
curl -X POST http://localhost:8080/api/v1/audio/transcriptions \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@recording.mp3" \
  -F "model=whisper-1"
```
**Response**
```json
{ "text": "Hello, this is a test recording." }
```

---

## 18. Retrieval / RAG

Base: `/api/v1/retrieval`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/config` | 🔒 | Full RAG config |
| POST | `/config/update` | 🔒 | Update config |
| GET | `/embedding` | 🔒 | Embedding model info |
| POST | `/embedding/update` | 🔒 | Change embedding model |
| POST | `/process/file` | ✅ | Embed an uploaded file |
| POST | `/process/text` | ✅ | Embed raw text |
| POST | `/process/youtube` | ✅ | Embed YouTube transcript |
| POST | `/process/web` | ✅ | Embed web page |
| POST | `/process/web/search` | ✅ | Web search + embed |
| POST | `/process/files/batch` | ✅ | Batch embed files |
| POST | `/query/doc` | ✅ | Query document |
| POST | `/query/collection` | ✅ | Query collection |
| POST | `/delete` | ✅ | Delete from vector store |
| POST | `/reset/db` | 🔒 | Wipe vector DB |
| POST | `/reset/uploads` | 🔒 | Delete uploads |

### `POST /api/v1/retrieval/process/file` ✅

Chunk and embed an already-uploaded file into the vector store.

**Request**
```json
{ "file_id": "file-uuid", "collection_name": "my_collection" }
```
**Response**
```json
{ "status": true, "collection_name": "my_collection", "file_id": "file-uuid" }
```

### `POST /api/v1/retrieval/query/collection` ✅

**Request**
```json
{
  "collection_names": ["my_collection"],
  "query": "What is the refund policy?",
  "k": 5,
  "r": 0.0,
  "hybrid": false
}
```
**Response**
```json
{
  "collection": "my_collection",
  "results": [
    { "id": "chunk-uuid", "content": "Refunds are processed within 5 business days..." }
  ]
}
```

### `POST /api/v1/retrieval/process/web/search` ✅

**Request**
```json
{ "query": "latest AI research 2025", "collection_name": "web_research" }
```

---

## 19. Pipelines

Base: `/api/v1/pipelines`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | 🔒 | List all pipelines |
| GET | `/list` | 🔒 | Paginated list |
| POST | `/upload` | 🔒 | Upload pipeline file |
| POST | `/add` | 🔒 | Add pipeline by URL |
| DELETE | `/delete` | 🔒 | Delete pipeline |
| GET | `/{id}/valves` | 🔒 | Pipeline valves |
| GET | `/{id}/valves/spec` | 🔒 | Valve schema |
| POST | `/{id}/valves/update` | 🔒 | Update valves |

---

## 20. Tasks

Base: `/api/v1/tasks`

AI-powered completion helpers for UI features.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/config` | 🔒 | Task config |
| POST | `/config/update` | 🔒 | Update |
| POST | `/title/completions` | ✅ | Generate chat title |
| POST | `/tags/completions` | ✅ | Suggest tags |
| POST | `/follow_up/completions` | ✅ | Follow-up suggestions |
| POST | `/queries/completions` | ✅ | RAG query generation |
| POST | `/image_prompt/completions` | ✅ | Image prompt from context |
| POST | `/emoji/completions` | ✅ | Emoji suggestion |
| POST | `/moa/completions` | ✅ | Mixture-of-Agents |
| POST | `/auto/completions` | ✅ | Auto task |

### `POST /api/v1/tasks/title/completions` ✅

**Request**
```json
{
  "model": "llama3",
  "messages": [{ "role": "user", "content": "What is quantum entanglement?" }]
}
```
**Response**
```json
{ "title": "Explaining Quantum Entanglement" }
```

---

## 21. Configs

Base: `/api/v1/configs`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | 🔒 | Full app config |
| POST | `/update` | 🔒 | Update config |
| GET | `/export` | 🔒 | Export as JSON |
| POST | `/import` | 🔒 | Import from JSON |
| GET | `/banners` | 🌐 | Active info banners |
| POST | `/banners/update` | 🔒 | Update banners |

---

## 22. Evaluations

Base: `/api/v1/evaluations`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/config` | 🔒 | Eval config |
| POST | `/config/update` | 🔒 | Update config |
| POST | `/feedback` | ✅ | Submit feedback |
| GET | `/feedback/{id}` | ✅ | Get feedback |
| POST | `/feedback/{id}/update` | ✅ | Update feedback |
| DELETE | `/feedback/{id}/delete` | ✅ | Delete |
| GET | `/feedback/all` | 🔒 | All feedback |
| GET | `/feedback/all/export` | 🔒 | Export as CSV |

### `POST /api/v1/evaluations/feedback` ✅

**Request**
```json
{
  "type": "rating",
  "data": { "rating": "like", "comment": "Great response!" },
  "meta": { "chat_id": "chat-uuid", "message_id": "msg-uuid", "model_id": "llama3" }
}
```

---

## 23. Analytics

Base: `/api/v1/analytics`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | 🔒 | Usage overview |
| GET | `/users` | 🔒 | Per-user stats |
| GET | `/models` | 🔒 | Per-model stats |

---

## 24. Jobs ⭐

Base: `/api/v1/jobs`

Async background job queue. Jobs are submitted, queued, and executed by a priority-based scheduler. Supports per-user priority, retries, archiving, and SSE push notifications.

### Quick Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/chat/completions` | ✅ | Submit job → 202 + job_id |
| GET | `/` | ✅ | List own jobs |
| GET | `/{job_id}` | ✅ | Poll status + result |
| DELETE | `/{job_id}` | ✅ | Cancel job |
| POST | `/{job_id}/retry` | 🔒 | Retry terminal job |
| GET | `/admin/list` | 🔒 | All jobs with filters |
| GET | `/events` | ✅ | SSE real-time events |
| GET | `/archive` | 🔒 | Archived jobs |
| GET | `/archive/config` | 🔒 | Retention settings |
| POST | `/archive/run` | 🔒 | Trigger archive sweep |
| GET | `/analytics` | 🔒 | Aggregate statistics |
| GET | `/analytics/export` | 🔒 | Download CSV |

---

### `POST /api/v1/jobs/chat/completions` ✅

Enqueue a chat-completion job. Returns **202** immediately.

**Request**
```json
{
  "model": "llama3",
  "messages": [
    { "role": "system", "content": "You are a concise assistant." },
    { "role": "user",   "content": "Summarise the history of Rome in 3 sentences." }
  ],
  "temperature": 0.7,
  "max_tokens": 512
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `model` | string | ✅ | Must exist in active MODELS |
| `messages` | array | ✅ | OpenAI-format |
| `temperature` | float | — | 0–2 |
| `max_tokens` | int | — | |
| `stream` | bool | — | Always forced to `false` |

**Response — 202**
```json
{
  "job_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "queued",
  "model_id": "llama3",
  "created_at": 1740170000
}
```

**Errors:** `404` model not found · `500` DB error

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

### `GET /api/v1/jobs/{job_id}` ✅

Poll job status. Terminal-job results are cached in Redis (10 s TTL).

**Query params:** `include_result=false` to skip payload while polling.

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

**Job statuses:** `queued` → `running` → `completed` | `failed` | `cancelled`

**Errors:** `403` not owner · `404` not found

```bash
# Polling loop
JOB_ID="3fa85f64-5717-4562-b3fc-2c963f66afa6"
while true; do
  STATUS=$(curl -s -H "Authorization: Bearer $TOKEN" \
    "http://localhost:8080/api/v1/jobs/$JOB_ID?include_result=false" | jq -r .status)
  [[ "$STATUS" =~ ^(completed|failed|cancelled)$ ]] && break
  sleep 3
done
# Get result
curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8080/api/v1/jobs/$JOB_ID" | jq .result
```

---

### `DELETE /api/v1/jobs/{job_id}` ✅

Cancel a queued or running job. If already terminal, returns current state without error.

**Errors:** `403` · `404`

```bash
curl -X DELETE http://localhost:8080/api/v1/jobs/$JOB_ID \
  -H "Authorization: Bearer $TOKEN"
```

---

### `POST /api/v1/jobs/{job_id}/retry` 🔒

Reset a `failed` or `cancelled` job back to `queued`. Clears `error`, resets `attempt_count` to 0.

**Errors:** `404` · `409` job not terminal

```bash
curl -X POST http://localhost:8080/api/v1/jobs/$JOB_ID/retry \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

### `GET /api/v1/jobs/` ✅

List own jobs. Newest first.

| Param | Type | Description |
|-------|------|-------------|
| `skip` | int | Offset (default 0) |
| `limit` | int | 1–200 (default 50) |
| `status` | string | `queued` \| `running` \| `completed` \| `failed` \| `cancelled` |
| `model_id` | string | Filter by model |

**Response**
```json
{ "jobs": [...], "total": 100, "skip": 0, "limit": 50 }
```

---

### `GET /api/v1/jobs/admin/list` 🔒

All users' jobs with filters.

| Param | Type | Description |
|-------|------|-------------|
| `skip/limit` | int | Pagination |
| `status` | string | Status filter |
| `model_id` | string | Model filter |
| `user_id` | string | User UUID filter |

---

### `GET /api/v1/jobs/events` ✅

**Server-Sent Events** stream. One connection per user, receives push events when jobs complete or fail.

```
data: {"ping": true}
data: {"job_id": "...", "status": "completed", "updated_at": 1740170045}
data: {"job_id": "...", "status": "failed", "error": "timeout", "updated_at": 1740170060}
: keepalive
```

```bash
curl -N -H "Authorization: Bearer $TOKEN" \
  http://localhost:8080/api/v1/jobs/events

# JavaScript
const es = new EventSource('/api/v1/jobs/events', {
  headers: { Authorization: `Bearer ${token}` }
});
es.onmessage = (e) => {
  const event = JSON.parse(e.data);
  if (!event.ping) console.log('Job event:', event);
};
```

---

### `GET /api/v1/jobs/archive` 🔒

| Param | Type | Description |
|-------|------|-------------|
| `skip/limit` | int | Pagination (limit max 200) |
| `status` | string | Filter |
| `model_id` | string | Filter |

---

### `POST /api/v1/jobs/archive/run` 🔒

Manually trigger archive sweep + purge.

**Response**
```json
{ "archived": 12, "purged": 3, "job_retention_days": 30, "job_archive_retention_days": 365 }
```

---

### `GET /api/v1/jobs/analytics` 🔒

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `combined` | bool | `true` | Include `job_archive` rows |

**Response**
```json
{
  "total": 1500,
  "includes_archive": true,
  "success_rate": 94.3,
  "avg_wait_seconds": 8,
  "by_status": { "completed": 1413, "failed": 62, "cancelled": 12, "queued": 8, "running": 5 },
  "by_model": [
    { "model_id": "llama3", "total": 900, "completed": 855, "failed": 30, "cancelled": 15 }
  ],
  "by_user": [
    { "user_id": "uuid", "name": "Alice", "email": "alice@example.com", "total": 320, "completed": 310, "failed": 8, "cancelled": 2 }
  ],
  "daily_history": [
    { "date": "2026-02-01", "total": 42, "completed": 40, "failed": 2 },
    { "date": "2026-02-20", "total": 88, "completed": 85, "failed": 3 }
  ]
}
```
> `daily_history` covers the last 90 days. SQLite + PostgreSQL compatible.

---

### `GET /api/v1/jobs/analytics/export` 🔒

Download analytics as CSV.

**Response** — `Content-Type: text/csv`, `Content-Disposition: attachment; filename=job_analytics.csv`
```csv
section,date,total,completed,failed
daily,2026-02-01,42,40,2
...

section,model_id,total,completed,failed
model,llama3,900,855,30
```

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  "http://localhost:8080/api/v1/jobs/analytics/export" \
  -o analytics.csv
```

---

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `JOB_RETENTION_DAYS` | `30` | Days before terminal job moves to archive |
| `JOB_ARCHIVE_RETENTION_DAYS` | `365` | Days before archive row is deleted (`0` = never) |

---

## 25. System ⭐

Base: `/api/v1/system`

### Quick Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/metrics` | 🔒 | Live CPU/RAM/disk + Ollama backends |
| GET | `/lb-strategy` | 🔒 | Current LB algorithm |
| POST | `/lb-strategy` | 🔒 | Set LB algorithm |
| GET | `/snapshots` | 🔒 | Time-series backend snapshots |

---

### `GET /api/v1/system/metrics` 🔒

**Response**
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
          { "name": "llama3:latest", "size_vram": 4661211136, "expires_at": "2026-02-21T20:00:00Z" }
        ]
      }
    }
  }
}
```

---

### `GET /api/v1/system/lb-strategy` 🔒

**Response**
```json
{
  "strategy": "least_connections",
  "available": ["fastest", "least_connections", "round_robin"],
  "source": "redis"
}
```

---

### `POST /api/v1/system/lb-strategy` 🔒

**Request**
```json
{ "strategy": "round_robin" }
```
**Response**
```json
{ "strategy": "round_robin", "saved": true }
```

**Errors:** `422` — invalid strategy

**Strategies:** `least_connections` (default) · `round_robin` · `fastest`

```bash
curl -X POST http://localhost:8080/api/v1/system/lb-strategy \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"strategy": "fastest"}'
```

---

### `GET /api/v1/system/snapshots` 🔒

Time-series backend metrics. One row per backend per snapshot interval.

| Param | Type | Default | Description |
|-------|------|---------|-------------|
| `limit` | int | `60` | Max snapshots per backend (1–500) |
| `since` | int | — | Unix epoch — only return newer rows |
| `backend_url` | string | — | Filter to one backend |

**Response**
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

```bash
# Last hour only (macOS)
SINCE=$(date -v-1H +%s)
curl "http://localhost:8080/api/v1/system/snapshots?since=$SINCE" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_LB_STRATEGY` | `least_connections` | Default when Redis unavailable |
| `BACKEND_SNAPSHOT_INTERVAL` | `300` | Seconds between snapshots |
| `BACKEND_SNAPSHOT_RETENTION_DAYS` | `7` | Days to keep snapshots |

---

## 26. Utils

Base: `/api/v1/utils`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/gravatar` | ✅ | Gravatar URL |
| POST | `/code/format` | ✅ | Format code |
| POST | `/code/execute` | ✅ | Execute code (sandboxed) |
| POST | `/markdown` | ✅ | Render markdown to HTML |
| POST | `/pdf` | ✅ | Render to PDF |
| GET | `/db/download` | 🔒 | Download SQLite DB |

### `POST /api/v1/utils/code/execute` ✅

**Request**
```json
{ "code": "print('hello world')", "language": "python" }
```
**Response**
```json
{ "stdout": "hello world\n", "stderr": "", "exit_code": 0 }
```

### `GET /api/v1/utils/db/download` 🔒

```bash
curl -H "Authorization: Bearer $ADMIN_TOKEN" \
  http://localhost:8080/api/v1/utils/db/download \
  -o backup.db
```

---

## 27. SCIM

Base: `/api/v1/scim/v2` *(requires `ENABLE_SCIM=true`)*

SCIM 2.0 compatible provisioning API. Bearer token must be a SCIM-specific configured secret.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ServiceProviderConfig` | 🌐 | Capabilities |
| GET | `/ResourceTypes` | 🌐 | Resource types |
| GET | `/Schemas` | 🌐 | Schema definitions |
| GET | `/Users` | 🔒 | List users |
| GET | `/Users/{user_id}` | 🔒 | Get user |
| POST | `/Users` | 🔒 | Create user |
| PUT | `/Users/{user_id}` | 🔒 | Replace user |
| PATCH | `/Users/{user_id}` | 🔒 | Update user |
| DELETE | `/Users/{user_id}` | 🔒 | Delete user |
| GET | `/Groups` | 🔒 | List groups |
| GET | `/Groups/{group_id}` | 🔒 | Get group |
| POST | `/Groups` | 🔒 | Create group |
| PUT | `/Groups/{group_id}` | 🔒 | Replace group |
| PATCH | `/Groups/{group_id}` | 🔒 | Update group |
| DELETE | `/Groups/{group_id}` | 🔒 | Delete group |

### `POST /api/v1/scim/v2/Users` 🔒

**Request**
```json
{
  "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
  "userName": "alice@example.com",
  "name": { "givenName": "Alice", "familyName": "Smith" },
  "emails": [{ "value": "alice@example.com", "primary": true }],
  "active": true
}
```

### `PATCH /api/v1/scim/v2/Users/{user_id}` 🔒

```json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [
    { "op": "replace", "path": "active", "value": false }
  ]
}
```

---

## 28. Ollama Proxy

Base: `/ollama`

Direct proxy to configured Ollama backends. Adds auth, load-balancing, token tracking, and VRAM stats.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/api/tags` | ✅ | List models |
| GET | `/api/ps` | ✅ | Loaded models + VRAM |
| POST | `/api/chat` | ✅ | Chat (streaming) |
| POST | `/api/generate` | ✅ | Generate |
| POST | `/api/embed` | ✅ | Embeddings |
| POST | `/api/pull` | 🔒 | Pull model |
| DELETE | `/api/delete` | 🔒 | Delete model |
| POST | `/v1/chat/completions` | ✅ | OpenAI-compatible chat |
| GET | `/v1/models` | ✅ | OpenAI-compatible model list |

Append `/{url_idx}` (e.g. `/api/chat/1`) to route to a specific backend by its index in `OLLAMA_BASE_URLS`.

### `POST /ollama/api/chat` ✅

**Request**
```json
{
  "model": "llama3",
  "messages": [{ "role": "user", "content": "Why is the sky blue?" }],
  "stream": true
}
```
**Response** — NDJSON stream or JSON

```bash
curl http://localhost:8080/ollama/api/chat \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama3","messages":[{"role":"user","content":"Hi"}],"stream":false}'
```

### `POST /ollama/v1/chat/completions` ✅

OpenAI-compatible. Accepts the same schema as `POST /openai/chat/completions`.

---

## 29. OpenAI Proxy

Base: `/openai`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/config` | 🔒 | API keys + endpoints config |
| POST | `/config/update` | 🔒 | Update config |
| GET | `/models` | ✅ | List models |
| POST | `/chat/completions` | ✅ | Chat completions |
| POST | `/responses` | ✅ | Responses API |
| POST | `/audio/speech` | ✅ | TTS |
| POST | `/verify` | 🔒 | Verify API key + endpoint |

### `POST /openai/chat/completions` ✅

Proxied and load-balanced across configured OpenAI-compatible endpoints.

**Request**
```json
{
  "model": "gpt-4o",
  "messages": [
    { "role": "system", "content": "You are helpful." },
    { "role": "user", "content": "What is 2 + 2?" }
  ],
  "stream": false
}
```
**Response — 200** — Standard OpenAI chat response

```bash
curl -X POST http://localhost:8080/openai/chat/completions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role":"user","content":"Hello!"}],
    "stream": false
  }'
```

---

## Common Response Codes

| Code | Meaning |
|------|---------|
| `200` | Success |
| `202` | Accepted (async job submitted) |
| `400` | Bad request / validation error |
| `401` | Missing or invalid token |
| `403` | Forbidden (not owner / not admin) |
| `404` | Resource not found |
| `409` | Conflict (e.g. retry non-terminal job) |
| `422` | Unprocessable entity (invalid param) |
| `500` | Internal server error |
