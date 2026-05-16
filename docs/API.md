# Hermes Agent — API Reference

## Table of Contents

1. [Authentication](#1-authentication)
2. [Base URL & Versioning](#2-base-url--versioning)
3. [Endpoints](#3-endpoints)
   - [POST /chat](#post-chat)
   - [GET /sessions/{user_id}](#get-sessionsuser_id)
   - [GET /memories/{user_id}](#get-memoriesuser_id)
   - [POST /memories/{user_id}](#post-memoriesuser_id)
   - [DELETE /memories/{user_id}](#delete-memoriesuser_id)
   - [POST /tasks](#post-tasks)
   - [GET /tasks/{task_id}](#get-taskstask_id)
   - [DELETE /tasks/{task_id}](#delete-taskstask_id)
   - [GET /tasks](#get-tasks)
   - [POST /scheduler/trigger](#post-schedulertrigger)
   - [POST /webhooks/telegram](#post-webhookstelegram)
   - [POST /webhooks/slack](#post-webhooksslack)
   - [POST /webhooks/teams](#post-webhooksteams)
4. [Models](#4-models)
5. [Error Codes](#5-error-codes)

---

## 1. Authentication

### Standard endpoints

All endpoints (except `/scheduler/trigger` and webhook endpoints) require a valid Google ID Token in the `Authorization` header:

```
Authorization: Bearer <Google ID Token>
```

The token is verified against Google's OAuth2 public keys. The `sub` claim is used as the canonical `user_id`. Requests with missing, expired, or invalid tokens are rejected with **HTTP 401**.

### Scheduler endpoint

`POST /scheduler/trigger` is invoked by Cloud Scheduler. It expects an OIDC token issued to the Cloud Scheduler service account, not a Google ID Token:

```
Authorization: Bearer <Cloud Scheduler OIDC Token>
```

### Webhook endpoints

Webhook endpoints use **platform-native verification** instead of Google ID Tokens:

| Endpoint | Verification mechanism |
|----------|----------------------|
| `POST /webhooks/telegram` | `X-Telegram-Bot-Api-Secret-Token` header matched against configured secret |
| `POST /webhooks/slack` | HMAC-SHA256 signature in `X-Slack-Signature` header |
| `POST /webhooks/teams` | Bot Framework JWT in `Authorization` header |

---

## 2. Base URL & Versioning

```
https://<cloud-run-service-url>/
```

The API is currently unversioned. All paths are at the root.

---

## 3. Endpoints

---

### POST /chat

Start or continue a conversation. Responses are streamed as **Server-Sent Events (SSE)**.

**Rate limit:** 20 requests per minute per IP address.

#### Request

```
POST /chat
Content-Type: application/json
Authorization: Bearer <Google ID Token>
Accept: text/event-stream
```

```json
{
  "message": "string",
  "session_id": "string | null"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | The user's message |
| `session_id` | string \| null | No | Existing session ID to continue. Omit or pass `null` to start a new session |

#### Response

The response is a stream of **Server-Sent Events**. Each event is a JSON-encoded `ChatEvent` object.

```
Content-Type: text/event-stream
```

**SSE event format:**

```
data: <ChatEvent JSON>\n\n
```

**ChatEvent types:**

- **`text`** — a chunk of the agent's response

```json
{
  "type": "text",
  "content": "Here is the answer...",
  "session_id": "session-abc123"
}
```

- **`done`** — the stream has completed successfully

```json
{
  "type": "done",
  "session_id": "session-abc123"
}
```

- **`error`** — an error occurred during processing

```json
{
  "type": "error",
  "content": "Policy violation: message blocked"
}
```

#### Error responses

| Status | Condition |
|--------|-----------|
| `400 Bad Request` | Message blocked by Model Armor screening |
| `400 Bad Request` | Message blocked by PolicyEngine (prompt or response) |
| `401 Unauthorized` | Missing or invalid Google ID Token |
| `429 Too Many Requests` | Rate limit exceeded (20 req/min) |
| `503 Service Unavailable` | Agent runner is not initialised |

---

### GET /sessions/{user_id}

List all sessions for a user.

#### Request

```
GET /sessions/{user_id}
Authorization: Bearer <Google ID Token>
```

| Path param | Description |
|-----------|-------------|
| `user_id` | The user's ID (must match the authenticated user's `sub` claim) |

#### Response `200 OK`

```json
{
  "sessions": [
    {
      "id": "session-abc123",
      "create_time": "2026-05-16T02:00:00Z"
    }
  ]
}
```

#### Error responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Missing or invalid token |
| `403 Forbidden` | `user_id` does not match the authenticated user |

---

### GET /memories/{user_id}

Retrieve episodic memories and profile facts for a user.

#### Request

```
GET /memories/{user_id}?query=<str>&top_k=<int>
Authorization: Bearer <Google ID Token>
```

| Parameter | Location | Type | Default | Description |
|-----------|----------|------|---------|-------------|
| `user_id` | path | string | — | Target user (must be authenticated user) |
| `query` | query string | string | `""` | Semantic search query to filter relevant memories |
| `top_k` | query string | integer | `10` | Maximum number of memory items to return |

#### Response `200 OK`

```json
{
  "memories": [
    "User prefers Python over JavaScript",
    "User is on the Platform Engineering team"
  ],
  "profiles": [
    {
      "scope": {
        "user_id": "user-123"
      },
      "facts": [
        "Prefers concise responses",
        "Works in UTC+1 timezone"
      ]
    }
  ]
}
```

#### Error responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Missing or invalid token |
| `403 Forbidden` | `user_id` does not match the authenticated user |

---

### POST /memories/{user_id}

Store a new memory fact for a user.

#### Request

```
POST /memories/{user_id}
Content-Type: application/json
Authorization: Bearer <Google ID Token>
```

```json
{
  "fact": "string"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fact` | string | Yes | The memory fact to store |

#### Response `201 Created`

```json
{
  "resource_name": "projects/my-project/locations/us-central1/memoryBanks/default/memories/mem-xyz",
  "fact": "User prefers Python over JavaScript"
}
```

#### Error responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Missing or invalid token |
| `403 Forbidden` | `user_id` does not match the authenticated user |
| `503 Service Unavailable` | Memory Bank is not configured |

---

### DELETE /memories/{user_id}

Delete **all** memory facts for a user.

#### Request

```
DELETE /memories/{user_id}
Authorization: Bearer <Google ID Token>
```

#### Response `204 No Content`

Empty body.

#### Error responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Missing or invalid token |
| `403 Forbidden` | `user_id` does not match the authenticated user |

---

### POST /tasks

Submit a long-running task for asynchronous execution by the TaskAgent.

**Rate limit:** 5 requests per minute per IP address.

#### Request

```
POST /tasks
Content-Type: application/json
Authorization: Bearer <Google ID Token>
```

```json
{
  "task": "string",
  "context": {}
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task` | string | Yes | Natural-language description of the task |
| `context` | object \| null | No | Optional arbitrary key-value context passed to the agent |

#### Response `202 Accepted`

```json
{
  "task_id": "task-abc123",
  "status": "pending",
  "created_at": "2026-05-16T02:00:00Z"
}
```

#### Error responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Missing or invalid token |
| `429 Too Many Requests` | Rate limit exceeded (5 req/min) |

---

### GET /tasks/{task_id}

Get the current state of a task.

#### Request

```
GET /tasks/{task_id}
Authorization: Bearer <Google ID Token>
```

#### Response `200 OK`

```json
{
  "task_id": "task-abc123",
  "user_id": "user-123",
  "status": "running",
  "task": "Analyse Q1 sales and produce a summary report",
  "progress": "Step 3 of 8: querying BigQuery...",
  "result": null,
  "error": null,
  "created_at": "2026-05-16T02:00:00Z",
  "completed_at": null
}
```

**Status values:**

| Value | Description |
|-------|-------------|
| `pending` | Task accepted, not yet started |
| `running` | TaskAgent is actively executing |
| `done` | Task completed successfully |
| `failed` | Task failed; see `error` field |
| `cancelled` | Task was cancelled via DELETE |

#### Error responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Missing or invalid token |
| `403 Forbidden` | Authenticated user does not own this task |
| `404 Not Found` | `task_id` does not exist |

---

### DELETE /tasks/{task_id}

Cancel a task.

#### Request

```
DELETE /tasks/{task_id}
Authorization: Bearer <Google ID Token>
```

#### Response `204 No Content`

Empty body. The task status is set to `cancelled`.

#### Error responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Missing or invalid token |
| `403 Forbidden` | Authenticated user does not own this task |
| `404 Not Found` | `task_id` does not exist |

---

### GET /tasks

List all tasks belonging to the authenticated user, most recent first.

#### Request

```
GET /tasks
Authorization: Bearer <Google ID Token>
```

#### Response `200 OK`

```json
{
  "tasks": [
    {
      "task_id": "task-abc123",
      "user_id": "user-123",
      "status": "done",
      "task": "Analyse Q1 sales...",
      "progress": "Completed",
      "result": "Report saved to gs://bucket/reports/q1.pdf",
      "error": null,
      "created_at": "2026-05-16T02:00:00Z",
      "completed_at": "2026-05-16T02:04:12Z"
    }
  ]
}
```

#### Error responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Missing or invalid token |

---

### POST /scheduler/trigger

Trigger a scheduled task. Called exclusively by Cloud Scheduler.

**Authentication:** Cloud Scheduler OIDC token (service account), **not** a Google ID Token.

#### Request

```
POST /scheduler/trigger
Content-Type: application/json
Authorization: Bearer <Cloud Scheduler OIDC Token>
```

```json
{
  "task": "string",
  "scheduled_by": "string",
  "job_name": "string"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `task` | string | Yes | Task description to execute |
| `scheduled_by` | string | Yes | Identifier of the scheduler service account |
| `job_name` | string | Yes | Cloud Scheduler job name for audit logging |

#### Response `202 Accepted`

```json
{
  "task_id": "task-scheduled-abc123",
  "status": "pending"
}
```

#### Error responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Invalid or missing OIDC token |

---

### POST /webhooks/telegram

Receive a Telegram Update.

#### Request

```
POST /webhooks/telegram
Content-Type: application/json
X-Telegram-Bot-Api-Secret-Token: <configured secret>
```

Body: Telegram `Update` object (see [Telegram Bot API docs](https://core.telegram.org/bots/api#update)).

#### Response `200 OK`

Empty body. Processing is asynchronous; the response is sent back to the user via the Telegram Bot API.

#### Error responses

| Status | Condition |
|--------|-----------|
| `403 Forbidden` | `X-Telegram-Bot-Api-Secret-Token` header missing or does not match |

---

### POST /webhooks/slack

Receive a Slack event (Events API).

#### Request

```
POST /webhooks/slack
Content-Type: application/json
X-Slack-Signature: v0=<hmac-sha256>
X-Slack-Request-Timestamp: <unix timestamp>
```

Body: Slack event payload. Handles `url_verification` challenge automatically.

#### Response `200 OK`

Empty body (or `{"challenge": "..."}` for URL verification). Response is sent back to the user via the Slack Web API.

#### Error responses

| Status | Condition |
|--------|-----------|
| `403 Forbidden` | HMAC signature verification failed |

---

### POST /webhooks/teams

Receive a Microsoft Teams Activity (Bot Framework).

#### Request

```
POST /webhooks/teams
Content-Type: application/json
Authorization: Bearer <Bot Framework JWT>
```

Body: Bot Framework `Activity` object.

#### Response `200 OK`

Empty body. Response is sent back to Teams via the Bot Framework REST API.

#### Error responses

| Status | Condition |
|--------|-----------|
| `401 Unauthorized` | Bot Framework JWT missing or invalid |

---

## 4. Models

### Request models

#### `ChatRequest`

```python
class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
```

#### `MemoryRequest`

```python
class MemoryRequest(BaseModel):
    fact: str
```

#### `TaskRequest`

```python
class TaskRequest(BaseModel):
    task: str
    context: dict | None = None
```

#### `SchedulerTriggerRequest`

```python
class SchedulerTriggerRequest(BaseModel):
    task: str
    scheduled_by: str
    job_name: str
```

### Response models

#### `ChatEvent`

```python
class ChatEvent(BaseModel):
    type: Literal["text", "done", "error"]
    content: str | None = None   # present on "text" and "error"
    session_id: str | None = None  # present on "text" and "done"
```

#### `SessionListResponse`

```python
class SessionInfo(BaseModel):
    id: str
    create_time: str  # ISO 8601

class SessionListResponse(BaseModel):
    sessions: list[SessionInfo]
```

#### `MemoryListResponse`

```python
class ProfileEntry(BaseModel):
    scope: dict
    facts: list[str]

class MemoryListResponse(BaseModel):
    memories: list[str]
    profiles: list[ProfileEntry]
```

#### `MemoryCreateResponse`

```python
class MemoryCreateResponse(BaseModel):
    resource_name: str
    fact: str
```

#### `TaskResponse`

```python
class TaskResponse(BaseModel):
    task_id: str
    user_id: str
    status: Literal["pending", "running", "done", "failed", "cancelled"]
    task: str
    progress: str | None = None
    result: str | None = None
    error: str | None = None
    created_at: str   # ISO 8601
    completed_at: str | None = None  # ISO 8601
```

#### `TaskCreateResponse`

```python
class TaskCreateResponse(BaseModel):
    task_id: str
    status: Literal["pending"]
    created_at: str  # ISO 8601
```

#### `TaskListResponse`

```python
class TaskListResponse(BaseModel):
    tasks: list[TaskResponse]
```

#### `SchedulerTriggerResponse`

```python
class SchedulerTriggerResponse(BaseModel):
    task_id: str
    status: str
```

---

## 5. Error Codes

### HTTP Status Codes

| Code | Meaning | Common causes |
|------|---------|---------------|
| `400 Bad Request` | Request rejected before or after agent processing | Model Armor blocked the prompt; PolicyEngine blocked the prompt or response |
| `401 Unauthorized` | Authentication failed | Missing `Authorization` header; expired token; invalid token signature |
| `403 Forbidden` | Authorisation denied | Accessing another user's sessions, memories, or tasks |
| `404 Not Found` | Resource does not exist | `task_id` not found |
| `422 Unprocessable Entity` | Request body failed validation | Missing required fields; wrong field types |
| `429 Too Many Requests` | Rate limit exceeded | `/chat` exceeds 20 req/min; `/tasks` exceeds 5 req/min |
| `503 Service Unavailable` | Backend service unavailable | Agent runner not initialised; Memory Bank not configured |

### Error response body

Non-SSE endpoints return errors in the standard FastAPI format:

```json
{
  "detail": "Human-readable error description"
}
```

For SSE endpoints (`/chat`), errors are delivered as a `ChatEvent` with `type: "error"` before the stream closes:

```json
{
  "type": "error",
  "content": "Policy violation: prompt blocked by enterprise policy rule HR-001"
}
```

### Rate limiting headers

When a rate limit is active, the following headers are included in the response:

```
X-RateLimit-Limit: 20
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1747360260
Retry-After: 43
```
