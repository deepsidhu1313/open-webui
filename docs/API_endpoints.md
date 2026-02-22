# Open WebUI — Complete API Reference

> Base URL: `http://<host>:8080`
> All `/api/v1/*` endpoints require `Authorization: Bearer <token>` unless noted.
> 🔒 = Admin only  |  ✅ = Any verified user  |  🌐 = Public / no auth

---

## Table of Contents

| Prefix | Router | Description |
|--------|--------|-------------|
| `/ollama` | [Ollama](#ollama) | Proxy to local Ollama backends |
| `/openai` | [OpenAI](#openai) | Proxy to OpenAI-compatible endpoints |
| `/api/v1/auths` | [Auths](#auths) | Authentication & session management |
| `/api/v1/users` | [Users](#users) | User management |
| `/api/v1/chats` | [Chats](#chats) | Chat history |
| `/api/v1/channels` | [Channels](#channels) | Channels & messages |
| `/api/v1/notes` | [Notes](#notes) | User notes |
| `/api/v1/models` | [Models](#models) | Model registry |
| `/api/v1/knowledge` | [Knowledge](#knowledge) | Knowledge bases / RAG |
| `/api/v1/prompts` | [Prompts](#prompts) | Prompt templates |
| `/api/v1/tools` | [Tools](#tools) | Tool (function) registry |
| `/api/v1/skills` | [Skills](#skills) | Skills registry |
| `/api/v1/functions` | [Functions](#functions) | Custom functions |
| `/api/v1/memories` | [Memories](#memories) | User memory store |
| `/api/v1/folders` | [Folders](#folders) | Chat folder organizer |
| `/api/v1/groups` | [Groups](#groups) | User groups |
| `/api/v1/files` | [Files](#files) | File upload & management |
| `/api/v1/images` | [Images](#images) | Image generation |
| `/api/v1/audio` | [Audio](#audio) | Speech-to-text / TTS |
| `/api/v1/retrieval` | [Retrieval](#retrieval) | RAG / vector store |
| `/api/v1/pipelines` | [Pipelines](#pipelines) | Pipeline management |
| `/api/v1/tasks` | [Tasks](#tasks) | AI task generation |
| `/api/v1/configs` | [Configs](#configs) | App configuration |
| `/api/v1/evaluations` | [Evaluations](#evaluations) | Chat evaluations / feedback |
| `/api/v1/analytics` | [Analytics](#analytics) | Usage analytics |
| `/api/v1/jobs` | [Jobs](#jobs) | Async job queue ⭐ New |
| `/api/v1/system` | [System](#system) | Server metrics & LB config ⭐ New |
| `/api/v1/utils` | [Utils](#utils) | Misc utilities |
| `/api/v1/scim/v2` | [SCIM](#scim) | SCIM 2.0 provisioning |

---

## Ollama

Proxy to configured Ollama backend(s). Pass `/{url_idx}` to target a specific backend by index.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ollama/config` | 🔒 | Get Ollama config (URLs, enabled flag) |
| POST | `/ollama/config/update` | 🔒 | Update Ollama config |
| GET | `/ollama/` | 🔒 | Ollama root (health check) |
| GET | `/ollama/url` | 🔒 | Get all configured backend URLs |
| POST | `/ollama/verify` | 🔒 | Verify a backend URL responds |
| GET | `/ollama/api/tags` | ✅ | List available models |
| GET | `/ollama/api/tags/{url_idx}` | ✅ | List models on a specific backend |
| GET | `/ollama/api/info` | ✅ | Model info |
| GET | `/ollama/api/info/{url_idx}` | ✅ | Model info on specific backend |
| GET | `/ollama/api/ps` | ✅ | Running/loaded models |
| GET | `/ollama/api/ps/{url_idx}` | ✅ | Loaded models on specific backend |
| POST | `/ollama/api/chat` | ✅ | Chat completions (streaming) |
| POST | `/ollama/api/chat/{url_idx}` | ✅ | Chat on specific backend |
| POST | `/ollama/api/generate` | ✅ | Text generation |
| POST | `/ollama/api/generate/{url_idx}` | ✅ | Generate on specific backend |
| POST | `/ollama/api/copy` | 🔒 | Copy a model |
| POST | `/ollama/api/copy/{url_idx}` | 🔒 | Copy on specific backend |
| DELETE | `/ollama/api/delete` | 🔒 | Delete a model |
| DELETE | `/ollama/api/delete/{url_idx}` | 🔒 | Delete on specific backend |
| POST | `/ollama/api/pull` | 🔒 | Pull a model |
| POST | `/ollama/api/pull/{url_idx}` | 🔒 | Pull on specific backend |
| POST | `/ollama/api/push` | 🔒 | Push a model |
| POST | `/ollama/api/push/{url_idx}` | 🔒 | Push on specific backend |
| POST | `/ollama/api/create` | 🔒 | Create a model |
| POST | `/ollama/api/create/{url_idx}` | 🔒 | Create on specific backend |
| POST | `/ollama/api/embed` | ✅ | Generate embeddings |
| POST | `/ollama/api/embed/{url_idx}` | ✅ | Embeddings on specific backend |
| POST | `/ollama/api/embeddings` | ✅ | Generate embeddings (legacy) |
| POST | `/ollama/api/embeddings/{url_idx}` | ✅ | Embeddings legacy on specific backend |
| POST | `/ollama/v1/completions` | ✅ | OpenAI-style completions |
| POST | `/ollama/v1/completions/{url_idx}` | ✅ | Completions on specific backend |
| POST | `/ollama/v1/chat/completions` | ✅ | OpenAI-style chat completions |
| POST | `/ollama/v1/chat/completions/{url_idx}` | ✅ | Chat completions on specific backend |
| GET | `/ollama/v1/models` | ✅ | List models (OpenAI format) |
| GET | `/ollama/v1/models/{url_idx}` | ✅ | Models on specific backend |
| POST | `/ollama/models/download` | 🔒 | Download a model |
| POST | `/ollama/models/download/{url_idx}` | 🔒 | Download on specific backend |
| POST | `/ollama/models/upload` | 🔒 | Upload a model |
| POST | `/ollama/models/upload/{url_idx}` | 🔒 | Upload on specific backend |

---

## OpenAI

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/openai/config` | 🔒 | Get OpenAI API config |
| POST | `/openai/config/update` | 🔒 | Update OpenAI API config |
| POST | `/openai/audio/speech` | ✅ | Text-to-speech |
| GET | `/openai/models` | ✅ | List models from all configured endpoints |
| GET | `/openai/models/{url_idx}` | ✅ | List models at specific endpoint |
| POST | `/openai/verify` | 🔒 | Verify OpenAI-compatible endpoint |
| POST | `/openai/chat/completions` | ✅ | Chat completion (proxied) |
| POST | `/openai/responses` | ✅ | Responses API |

---

## Auths

Base: `/api/v1/auths`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | Get current session info |
| POST | `/signin` | 🌐 | Sign in with email + password |
| POST | `/signup` | 🌐 | Register new account |
| POST | `/signout` | ✅ | Invalidate current session |
| POST | `/add` | 🔒 | Admin: create a user account |
| GET | `/profile` | ✅ | Get own profile |
| GET | `/config` | 🔒 | Get auth config (LDAP, OAuth, etc.) |
| POST | `/config/update` | 🔒 | Update auth config |
| GET | `/admin/config` | 🔒 | Get admin-level auth config |
| POST | `/admin/config/update` | 🔒 | Update admin auth config |
| POST | `/admin/details` | 🔒 | Get detailed user info by email |
| GET | `/token` | 🌐 | Get token (OAuth callback) |
| GET | `/token/config` | 🔒 | Get token config |
| POST | `/token/config/update` | 🔒 | Update token config |
| GET | `/oauth/config` | 🔒 | Get OAuth provider config |
| POST | `/oauth/config/update` | 🔒 | Update OAuth config |
| GET | `/oauth/providers` | 🌐 | List enabled OAuth providers |
| GET | `/oauth/{provider}/login` | 🌐 | Initiate OAuth login |
| GET | `/oauth/{provider}/callback` | 🌐 | OAuth callback |
| POST | `/password/update` | ✅ | Update own password |
| POST | `/api_key` | ✅ | Regenerate API key |
| GET | `/api_key` | ✅ | Get current API key |
| DELETE | `/api_key` | ✅ | Delete API key |
| GET | `/ldap/config` | 🔒 | Get LDAP config |
| POST | `/ldap/config/update` | 🔒 | Update LDAP config |
| POST | `/ldap/signin` | 🌐 | LDAP sign in |

---

## Users

Base: `/api/v1/users`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | 🔒 | List users (paginated) |
| GET | `/all` | 🔒 | List all users (no pagination) |
| GET | `/search` | 🔒 | Search users by name/email |
| GET | `/groups` | ✅ | Get groups the current user belongs to |
| GET | `/permissions` | ✅ | Get effective permissions |
| GET | `/default/permissions` | 🔒 | Get default user permissions |
| POST | `/default/permissions` | 🔒 | Update default permissions |
| GET | `/user/settings` | ✅ | Get own UI settings |
| POST | `/user/settings/update` | ✅ | Update own UI settings |
| GET | `/user/status` | ✅ | Get own status |
| POST | `/user/status/update` | ✅ | Update own status |
| GET | `/user/info` | ✅ | Get own custom info |
| POST | `/user/info/update` | ✅ | Update own custom info |
| GET | `/{user_id}` | 🔒 | Get user by ID |
| GET | `/{user_id}/info` | 🔒 | Get user custom info |
| GET | `/{user_id}/oauth/sessions` | 🔒 | List OAuth sessions |
| GET | `/{user_id}/profile/image` | 🌐 | Get profile image |
| GET | `/{user_id}/active` | 🔒 | Check if user is active |
| POST | `/{user_id}/update` | 🔒 | Update user |
| DELETE | `/{user_id}` | 🔒 | Delete user |
| GET | `/{user_id}/groups` | 🔒 | List groups for a user |
| PATCH | `/{user_id}/job-priority` | 🔒 | Update job queue priority (1–10) |

---

## Chats

Base: `/api/v1/chats`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List own chats |
| GET | `/list` | ✅ | List chats (alias) |
| GET | `/list/user/{user_id}` | 🔒 | List chats for another user |
| GET | `/all` | ✅ | All chats (no pagination) |
| GET | `/all/tags` | ✅ | All tags across chats |
| GET | `/all/archived` | ✅ | All archived chats |
| GET | `/archived` | ✅ | Archived chats (paginated) |
| GET | `/pinned` | ✅ | Pinned chats |
| GET | `/search` | ✅ | Search chats |
| GET | `/folder/{folder_id}` | ✅ | Chats in a folder |
| GET | `/tags/list` | ✅ | List all tags |
| GET | `/tags/all` | ✅ | All tagged chats |
| POST | `/new` | ✅ | Create new chat |
| POST | `/import` | ✅ | Import chats |
| GET | `/export` | ✅ | Export all chats |
| DELETE | `/` | ✅ | Delete all own chats |
| POST | `/{id}` | ✅ | Get chat by ID |
| GET | `/{id}` | ✅ | Get chat by ID (GET variant) |
| DELETE | `/{id}` | ✅ | Delete a chat |
| POST | `/{id}/archive` | ✅ | Archive a chat |
| GET | `/{id}/clone` | ✅ | Clone a chat |
| POST | `/{id}/pin` | ✅ | Pin a chat |
| POST | `/{id}/share` | ✅ | Share a chat |
| DELETE | `/{id}/share` | ✅ | Remove share |
| GET | `/{id}/tags` | ✅ | List chat tags |
| POST | `/{id}/tags/new` | ✅ | Add tag |
| DELETE | `/{id}/tags` | ✅ | Remove tag |
| GET | `/{id}/messages` | ✅ | Get messages |
| GET | `/{id}/messages/{message_id}` | ✅ | Get single message |
| POST | `/{id}/messages/post` | ✅ | Add message |
| DELETE | `/{id}/messages` | ✅ | Delete all messages |
| GET | `/{id}/suggestions` | ✅ | Get suggestions |

---

## Channels

Base: `/api/v1/channels`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List channels |
| POST | `/create` | 🔒 | Create channel |
| GET | `/{id}` | ✅ | Get channel |
| POST | `/{id}/update` | 🔒 | Update channel |
| DELETE | `/{id}/delete` | 🔒 | Delete channel |
| GET | `/{id}/members` | ✅ | List members |
| POST | `/{id}/members/add` | 🔒 | Add member |
| DELETE | `/{id}/members/{user_id}` | 🔒 | Remove member |
| GET | `/{id}/messages` | ✅ | Get messages |
| POST | `/{id}/messages/post` | ✅ | Post message |
| GET | `/{id}/messages/{message_id}` | ✅ | Get single message |
| POST | `/{id}/messages/{message_id}/update` | ✅ | Edit message |
| DELETE | `/{id}/messages/{message_id}/delete` | ✅ | Delete message |
| POST | `/{id}/messages/{message_id}/reactions` | ✅ | Add reaction |
| DELETE | `/{id}/messages/{message_id}/reactions` | ✅ | Remove reaction |

---

## Notes

Base: `/api/v1/notes`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List own notes |
| GET | `/list` | ✅ | List notes (paginated) |
| POST | `/create` | ✅ | Create note |
| GET | `/id/{id}` | ✅ | Get note |
| POST | `/id/{id}/update` | ✅ | Update note |
| DELETE | `/id/{id}/delete` | ✅ | Delete note |

---

## Models

Base: `/api/v1/models`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List all available models (merged from Ollama + OpenAI + custom) |
| GET | `/base` | 🔒 | List custom base model definitions |
| POST | `/create` | 🔒 | Create custom model entry |
| GET | `/id/{id}` | ✅ | Get model by ID |
| POST | `/id/{id}/update` | 🔒 | Update model |
| DELETE | `/id/{id}/delete` | 🔒 | Delete model |
| POST | `/id/{id}/access/update` | 🔒 | Update model visibility |
| GET | `/id/{id}/toggle` | 🔒 | Toggle model enabled |

---

## Knowledge

Base: `/api/v1/knowledge`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List knowledge bases |
| GET | `/list` | ✅ | List (alias) |
| POST | `/create` | ✅ | Create knowledge base |
| GET | `/{id}` | ✅ | Get knowledge base |
| POST | `/{id}/update` | ✅ | Update metadata |
| POST | `/{id}/access/update` | 🔒 | Update access |
| DELETE | `/{id}/delete` | ✅ | Delete knowledge base |
| POST | `/{id}/file/add` | ✅ | Add file to knowledge base |
| POST | `/{id}/file/update` | ✅ | Update file |
| POST | `/{id}/file/remove` | ✅ | Remove file |
| POST | `/{id}/files/batch/add` | ✅ | Add multiple files |
| POST | `/{id}/reset` | ✅ | Reset / re-index |

---

## Prompts

Base: `/api/v1/prompts`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List prompts |
| GET | `/tags` | ✅ | List tags |
| GET | `/list` | ✅ | Paginated list |
| POST | `/create` | ✅ | Create prompt |
| GET | `/command/{command}` | ✅ | Get prompt by slash command |
| GET | `/id/{id}` | ✅ | Get prompt |
| POST | `/id/{id}/update` | ✅ | Update prompt |
| POST | `/id/{id}/update/meta` | ✅ | Update metadata only |
| POST | `/id/{id}/update/version` | ✅ | Save new version |
| POST | `/id/{id}/access/update` | 🔒 | Update access |
| DELETE | `/id/{id}/delete` | ✅ | Delete prompt |
| GET | `/id/{id}/history` | ✅ | List versions |
| GET | `/id/{id}/history/{history_id}` | ✅ | Get a version |
| DELETE | `/id/{id}/history/{history_id}` | ✅ | Delete a version |
| GET | `/id/{id}/history/diff` | ✅ | Diff two versions |

---

## Tools

Base: `/api/v1/tools`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List tools |
| GET | `/list` | ✅ | Paginated list |
| POST | `/load/url` | ✅ | Load tool from URL |
| GET | `/export` | 🔒 | Export all tools |
| POST | `/create` | ✅ | Create tool |
| GET | `/id/{id}` | ✅ | Get tool |
| POST | `/id/{id}/update` | ✅ | Update tool |
| POST | `/id/{id}/access/update` | 🔒 | Update access |
| DELETE | `/id/{id}/delete` | ✅ | Delete tool |
| GET | `/id/{id}/valves` | ✅ | Get admin valves |
| GET | `/id/{id}/valves/spec` | ✅ | Valve schema |
| POST | `/id/{id}/valves/update` | 🔒 | Update admin valves |
| GET | `/id/{id}/valves/user` | ✅ | Get user valves |
| GET | `/id/{id}/valves/user/spec` | ✅ | User valve schema |
| POST | `/id/{id}/valves/user/update` | ✅ | Update user valves |

---

## Skills

Base: `/api/v1/skills`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List skills |
| GET | `/list` | ✅ | Paginated list |
| GET | `/export` | 🔒 | Export all skills |
| POST | `/create` | ✅ | Create skill |
| GET | `/id/{id}` | ✅ | Get skill |
| POST | `/id/{id}/update` | ✅ | Update skill |
| POST | `/id/{id}/access/update` | 🔒 | Update access |
| POST | `/id/{id}/toggle` | 🔒 | Toggle enabled |
| DELETE | `/id/{id}/delete` | ✅ | Delete skill |

---

## Functions

Base: `/api/v1/functions`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List functions |
| GET | `/list` | ✅ | Paginated list |
| GET | `/export` | 🔒 | Export all |
| POST | `/create` | ✅ | Create function |
| GET | `/id/{id}` | ✅ | Get function |
| POST | `/id/{id}/update` | ✅ | Update function |
| DELETE | `/id/{id}/delete` | ✅ | Delete function |
| GET | `/id/{id}/toggle` | 🔒 | Toggle enabled |
| GET | `/id/{id}/toggle/global` | 🔒 | Toggle global |
| GET | `/id/{id}/valves` | ✅ | Get admin valves |
| GET | `/id/{id}/valves/spec` | ✅ | Valve schema |
| POST | `/id/{id}/valves/update` | 🔒 | Update admin valves |
| GET | `/id/{id}/valves/user` | ✅ | Get user valves |
| GET | `/id/{id}/valves/user/spec` | ✅ | User valve schema |
| POST | `/id/{id}/valves/user/update` | ✅ | Update user valves |

---

## Memories

Base: `/api/v1/memories`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List own memories |
| POST | `/add` | ✅ | Add a memory |
| POST | `/query` | ✅ | Semantic search over memories |
| DELETE | `/` | ✅ | Delete all own memories |
| POST | `/{id}/update` | ✅ | Update a memory |
| DELETE | `/{id}` | ✅ | Delete a memory |

---

## Folders

Base: `/api/v1/folders`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List own folders |
| POST | `/create` | ✅ | Create folder |
| GET | `/id/{id}` | ✅ | Get folder |
| POST | `/id/{id}/update` | ✅ | Rename folder |
| DELETE | `/id/{id}/delete` | ✅ | Delete folder (and optionally chats) |
| POST | `/id/{id}/chats` | ✅ | Add chats to folder |
| DELETE | `/id/{id}/chats/{chat_id}` | ✅ | Remove chat from folder |

---

## Groups

Base: `/api/v1/groups`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | 🔒 | List groups |
| POST | `/create` | 🔒 | Create group |
| GET | `/id/{id}` | 🔒 | Get group |
| POST | `/id/{id}/update` | 🔒 | Update group |
| DELETE | `/id/{id}/delete` | 🔒 | Delete group |
| POST | `/id/{id}/users/add` | 🔒 | Add users to group |
| DELETE | `/id/{id}/users/delete` | 🔒 | Remove users from group |

---

## Files

Base: `/api/v1/files`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/` | ✅ | Upload file |
| GET | `/` | ✅ | List own files |
| GET | `/config` | 🔒 | Get file storage config |
| POST | `/config/update` | 🔒 | Update file storage config |
| GET | `/{id}` | ✅ | Get file metadata |
| GET | `/{id}/content` | ✅ | Download file content |
| GET | `/{id}/content/html` | ✅ | Get content as HTML |
| GET | `/{id}/content/{file_name}` | ✅ | Download with specific filename |
| POST | `/{id}/data/content/update` | ✅ | Update extracted text content |
| DELETE | `/{id}` | ✅ | Delete file |

---

## Images

Base: `/api/v1/images`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/config` | 🔒 | Get image generation config |
| POST | `/config/update` | 🔒 | Update image gen config |
| GET | `/models` | ✅ | List available image models |
| GET | `/models/default` | 🔒 | Get default model |
| POST | `/models/default/update` | 🔒 | Set default model |
| GET | `/size` | 🔒 | Get default image size |
| POST | `/size/update` | 🔒 | Update default size |
| GET | `/steps` | 🔒 | Get inference steps |
| POST | `/steps/update` | 🔒 | Update steps |
| POST | `/generations` | ✅ | Generate image(s) |

---

## Audio

Base: `/api/v1/audio`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/config` | 🔒 | Get STT / TTS config |
| POST | `/config/update` | 🔒 | Update audio config |
| GET | `/tts` | 🔒 | Get TTS config |
| POST | `/tts/update` | 🔒 | Update TTS config |
| GET | `/stt` | 🔒 | Get STT config |
| POST | `/stt/update` | 🔒 | Update STT config |
| POST | `/speech` | ✅ | Text → speech audio |
| POST | `/transcriptions` | ✅ | Audio file → text |

---

## Retrieval

Base: `/api/v1/retrieval`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | 🔒 | Get RAG config |
| GET | `/embedding` | 🔒 | Get embedding config |
| POST | `/embedding/update` | 🔒 | Update embedding model |
| GET | `/config` | 🔒 | Full retrieval config |
| POST | `/config/update` | 🔒 | Update retrieval config |
| POST | `/process/file` | ✅ | Process & embed a file |
| POST | `/process/text` | ✅ | Process & embed raw text |
| POST | `/process/youtube` | ✅ | Process YouTube video transcript |
| POST | `/process/web` | ✅ | Process web page |
| POST | `/process/web/search` | ✅ | Web search + process results |
| POST | `/query/doc` | ✅ | Query single document |
| POST | `/query/collection` | ✅ | Query a collection |
| POST | `/delete` | ✅ | Delete from vector store |
| POST | `/reset/db` | 🔒 | Wipe vector DB |
| POST | `/reset/uploads` | 🔒 | Delete uploaded files |
| GET | `/ef/{text}` | ✅ | Embed a text string (debug) |
| POST | `/process/files/batch` | ✅ | Batch process files |

---

## Pipelines

Base: `/api/v1/pipelines`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/list` | 🔒 | List pipelines |
| POST | `/upload` | 🔒 | Upload pipeline file |
| POST | `/add` | 🔒 | Add pipeline by URL |
| DELETE | `/delete` | 🔒 | Delete pipeline |
| GET | `/` | 🔒 | List all pipelines |
| GET | `/{pipeline_id}/valves` | 🔒 | Get pipeline valves |
| GET | `/{pipeline_id}/valves/spec` | 🔒 | Valve schema |
| POST | `/{pipeline_id}/valves/update` | 🔒 | Update valves |

---

## Tasks

Base: `/api/v1/tasks`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/active/chats` | ✅ | List active chat tasks |
| GET | `/config` | 🔒 | Get task config |
| POST | `/config/update` | 🔒 | Update task config |
| POST | `/title/completions` | ✅ | Generate chat title |
| POST | `/follow_up/completions` | ✅ | Generate follow-up suggestions |
| POST | `/tags/completions` | ✅ | Suggest tags for chat |
| POST | `/image_prompt/completions` | ✅ | Generate image prompt from context |
| POST | `/queries/completions` | ✅ | Generate RAG queries |
| POST | `/auto/completions` | ✅ | Automatic task completion |
| POST | `/emoji/completions` | ✅ | Suggest emoji for message |
| POST | `/moa/completions` | ✅ | Mixture-of-Agents aggregation |

---

## Configs

Base: `/api/v1/configs`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | 🔒 | Get full app config |
| POST | `/update` | 🔒 | Update app config |
| POST | `/import` | 🔒 | Import config from JSON |
| GET | `/export` | 🔒 | Export config to JSON |
| GET | `/banners` | 🌐 | Get current banners |
| POST | `/banners/update` | 🔒 | Update banners |

---

## Evaluations

Base: `/api/v1/evaluations`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | ✅ | List own evaluations |
| GET | `/config` | 🔒 | Get evaluation config |
| POST | `/config/update` | 🔒 | Update config |
| POST | `/feedback` | ✅ | Submit chat feedback |
| GET | `/feedback/{id}` | ✅ | Get feedback |
| POST | `/feedback/{id}/update` | ✅ | Update feedback |
| DELETE | `/feedback/{id}/delete` | ✅ | Delete feedback |
| GET | `/feedback/all` | 🔒 | List all feedback |
| GET | `/feedback/all/export` | 🔒 | Export feedback as CSV |

---

## Analytics

Base: `/api/v1/analytics`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | 🔒 | Get usage analytics |
| GET | `/users` | 🔒 | Per-user analytics |
| GET | `/models` | 🔒 | Per-model analytics |

---

## Jobs ⭐

Base: `/api/v1/jobs`

> Async chat-completion job queue with priority scheduling, retries, archiving, and SSE push notifications.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/chat/completions` | ✅ | Submit async chat job → 202 + job_id |
| GET | `/` | ✅ | List own jobs (paginated, filterable) |
| GET | `/{job_id}` | ✅ | Poll job status + result |
| DELETE | `/{job_id}` | ✅ | Cancel a job |
| POST | `/{job_id}/retry` | 🔒 | Retry a terminal job |
| GET | `/admin/list` | 🔒 | Admin: all jobs with filters |
| GET | `/events` | ✅ | SSE stream of real-time job events |
| GET | `/archive` | 🔒 | Browse archived jobs |
| GET | `/archive/config` | 🔒 | Retention policy config |
| POST | `/archive/run` | 🔒 | Manually trigger archive sweep |
| GET | `/analytics` | 🔒 | Aggregate stats (active + archive) |
| GET | `/analytics/export` | 🔒 | Download analytics as CSV |

**Query params for `GET /`:**

| Param | Type | Description |
|-------|------|-------------|
| `skip` | int | Pagination offset (default 0) |
| `limit` | int | Max results, 1–200 (default 50) |
| `status` | string | `queued` \| `running` \| `completed` \| `failed` \| `cancelled` |
| `model_id` | string | Filter by model |

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `JOB_RETENTION_DAYS` | `30` | Days before terminal job is archived |
| `JOB_ARCHIVE_RETENTION_DAYS` | `365` | Days before archive row is deleted (0 = never) |

---

## System ⭐

Base: `/api/v1/system`

> Server metrics, load-balancing configuration, and time-series backend snapshots.

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/metrics` | 🔒 | Live CPU%, RAM%, disk%, Ollama /api/ps data |
| GET | `/lb-strategy` | 🔒 | Get current Ollama LB algorithm |
| POST | `/lb-strategy` | 🔒 | Set LB algorithm (persisted to Redis) |
| GET | `/snapshots` | 🔒 | Time-series backend snapshots |

**LB Strategies:** `least_connections` (default) · `round_robin` · `fastest`

**Query params for `GET /snapshots`:**

| Param | Type | Description |
|-------|------|-------------|
| `limit` | int | Max snapshots per backend, 1–500 (default 60) |
| `since` | int | Unix epoch — only return newer snapshots |
| `backend_url` | string | Filter to a single backend URL |

**Environment variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_LB_STRATEGY` | `least_connections` | Default LB when Redis unavailable |
| `BACKEND_SNAPSHOT_INTERVAL` | `300` | Seconds between snapshots |
| `BACKEND_SNAPSHOT_RETENTION_DAYS` | `7` | Days to retain snapshot rows |

---

## Utils

Base: `/api/v1/utils`

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/gravatar` | ✅ | Get Gravatar URL for an email |
| POST | `/code/format` | ✅ | Auto-format code snippet |
| POST | `/code/execute` | ✅ | Execute code (sandboxed) |
| POST | `/markdown` | ✅ | Render markdown to HTML |
| POST | `/pdf` | ✅ | Render content to PDF |
| GET | `/db/download` | 🔒 | Download SQLite DB file |

---

## SCIM

Base: `/api/v1/scim/v2` *(requires `ENABLE_SCIM=true`)*

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/ServiceProviderConfig` | 🌐 | SCIM service provider capabilities |
| GET | `/ResourceTypes` | 🌐 | Supported resource types |
| GET | `/Schemas` | 🌐 | SCIM schemas |
| GET | `/Users` | 🔒 | List users (SCIM) |
| GET | `/Users/{user_id}` | 🔒 | Get user (SCIM) |
| POST | `/Users` | 🔒 | Create user (SCIM) |
| PUT | `/Users/{user_id}` | 🔒 | Replace user (SCIM) |
| PATCH | `/Users/{user_id}` | 🔒 | Update user (SCIM) |
| DELETE | `/Users/{user_id}` | 🔒 | Delete user (SCIM) |
| GET | `/Groups` | 🔒 | List groups (SCIM) |
| GET | `/Groups/{group_id}` | 🔒 | Get group (SCIM) |
| POST | `/Groups` | 🔒 | Create group (SCIM) |
| PUT | `/Groups/{group_id}` | 🔒 | Replace group (SCIM) |
| PATCH | `/Groups/{group_id}` | 🔒 | Update group (SCIM) |
| DELETE | `/Groups/{group_id}` | 🔒 | Delete group (SCIM) |

---

## Auth Legend

| Symbol | Meaning |
|--------|---------|
| 🌐 | Public — no authentication required |
| ✅ | Any verified (logged-in) user |
| 🔒 | Admin (`role=admin`) only |

> API keys work as bearer tokens for all ✅ and 🔒 endpoints:
> `Authorization: Bearer sk-...`
