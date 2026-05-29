# Personal Telegram Assistant
## Specification — Stage 2: Telegram Gateway

> **Assumes:** Stage 1d complete and merged to `main` — `python main.py` runs the
> full agent loop from CLI, tasks and calendar events appear in Google, emails send,
> every exchange written to SQLite `agent_turns`. `AgentDeps`, `SupervisorAgent`,
> `SpecialistAgent`, `core/registry.py`, and `SQLiteStore` are all stable. Google
> OAuth credentials are cached on disk from Stage 1b.
>
> **Branch:** `stage/2` branched from `main` after Stage 1d merge
>
> **Done when:** Sending a Telegram message to your bot creates a Google Task,
> calendar event, or sends an email — exactly as Stage 1d did from CLI. The same
> agent loop runs unchanged. The only difference is how the user's message arrives.

---

## 1. What Stage 2 Adds

Stage 1d proved the full agent loop works end-to-end from a CLI prompt. Stage 2
replaces `main.py` as the entry point with a FastAPI gateway that receives Telegram
webhook POSTs and replies via the Telegram Bot API. Nothing inside `agents/`,
`schemas/`, `memory/`, or `core/` changes — the agent loop is called identically.
Only the entry point is new.

`main.py` is NOT deleted. It still works for CLI testing and remains the
development entry point throughout this stage.

New pieces introduced this stage:

- **`gateway/`** — FastAPI app and Telegram send helper
- **`Dockerfile`** — packages the whole project into a portable container image
- **Telegram bot** — created via BotFather, token stored in `.env`
- **ngrok** — tunnels localhost to a public HTTPS URL for local webhook testing

---

## 2. Why FastAPI and Not a Raw HTTP Server

Telegram delivers messages to your bot by making an HTTPS POST to a webhook URL
you register. Your server must be reachable from the internet and must respond
with `200 OK` within 30 seconds or Telegram retries the delivery.

FastAPI is the right choice here for three reasons:

**1. Minimal boilerplate.** A working webhook endpoint is under 50 lines. FastAPI
handles request parsing, response encoding, and async execution out of the box.

**2. Lifespan hooks.** FastAPI's `lifespan` context manager runs startup and
shutdown logic once per process — not per request. This is where the Supervisor,
SQLite store, and later the persistent MCP server manager will be initialised.
Resources created in lifespan are shared across all requests.

**3. Forward compatibility.** The same FastAPI app will gain additional endpoints
in later stages — OAuth callbacks, health checks, and a status endpoint. Starting
with FastAPI means no rewrite later.

---

## 3. Why Telegram Webhooks and Not Polling

Telegram supports two ways to receive messages:

**Polling** — your code calls `getUpdates` on a loop, asking Telegram "any new
messages?" This is simpler to set up (no public URL needed) but burns CPU
constantly and adds latency proportional to your polling interval.

**Webhooks** — Telegram calls your server immediately when a message arrives.
Zero polling overhead, instant delivery. This is the correct approach for any
production assistant.

The tradeoff is that webhooks require a publicly reachable HTTPS URL. For local
development, ngrok solves this without any server setup.

---

## 4. Why ngrok for Local Development

Telegram's webhook endpoint must be HTTPS. During local development you do not
have a public server or a TLS certificate — ngrok provides both in one command.

ngrok creates a secure tunnel from a public `https://` URL to your local
`localhost:8000`. Telegram sends webhook POSTs to the ngrok URL, ngrok forwards
them to your local uvicorn process, and your response travels back the same way.

This means you can develop and test the full Telegram → agent → reply flow
entirely on your local machine, with real messages from your phone, before any
Docker or server is involved. The ngrok URL changes on every free-tier restart,
so you re-register the webhook each session — this is a minor inconvenience
acceptable for development.

---

## 5. Why Docker Is Introduced Here

Docker is introduced in Phase 3 of this stage for one reason: **portability**.
Once the gateway works locally via uvicorn, packaging it into a Docker image
ensures it will run identically on any server you choose to deploy to later.

The deployment decision — which hosting provider, which region, which plan — is
deliberately deferred. By the end of this stage you will have a tested Docker
image that can be deployed anywhere. The hosting-specific concerns (HTTPS
termination, credential storage, process supervision) are solved when you make
that choice, not now.

This is a deliberate reversal of the typical approach of designing for a specific
host from the start. It keeps Stage 2 focused on one problem: getting the gateway
working.

---

## 6. How Credentials Work in This Stage

In Stage 1d, `workspace-mcp` read your Google OAuth credentials directly from
disk at `%APPDATA%\workspace-mcp\credentials\your-email@gmail.com.json` on
Windows. Nothing changes for Phase 2 (local uvicorn) — credentials are still
read from disk.

For Phase 3 (Docker), the credential file must be available inside the container.
The cleanest solution for local Docker is a **volume mount** — you tell Docker
to make your local credential directory visible inside the container at the path
`workspace-mcp` expects. No copying, no encoding, no environment variable tricks.
The credential file stays on your host machine and the container reads it directly.

This approach works for any hosting provider with a persistent filesystem. For
providers with ephemeral filesystems (e.g. Render free tier), a different
mechanism is needed — that is addressed in a deployment appendix when a host is
chosen.

---

## 7. Architecture

```
Telegram App (your phone)
        │
        │  HTTPS POST /webhook/{secret}
        ▼
ngrok tunnel (Phase 2 + 3)  /  hosting provider (Phase 4+)
        │
        ▼
FastAPI Gateway  (uvicorn locally / Docker container)
        │
        ├── validates secret token
        ├── validates chat_id allowlist
        ├── extracts message text
        ├── builds AgentDeps
        ├── calls SupervisorAgent.run(text, deps)
        │         │
        │         └── SpecialistAgent[key] (one or more, via registry)
        │                   │
        │                   └── workspace-mcp subprocess (narrow tool surface)
        │                             └── Google Tasks / Calendar / Gmail
        │
        ├── sends reply via Telegram Bot API
        └── writes TurnRecord to SQLite
```

**Security model — two layers of protection:**

- **`WEBHOOK_SECRET`** — a random token in the webhook URL path. Only Telegram,
  which knows the full URL, can trigger the endpoint. Random internet traffic
  hitting `/webhook/` gets a 403.
- **`TELEGRAM_CHAT_ID` allowlist** — even if someone guesses the webhook URL,
  only messages from your registered chat_id are processed. All others are
  silently ignored with a log warning.

---

## 8. Three Phases

Each phase must be fully validated before moving to the next. Do not skip ahead.

**Phase 1 — Telegram bot and tooling setup**

Create the Telegram bot via BotFather, get your credentials, install ngrok.
No code is written in this phase. These are prerequisites for everything that follows.

Pass/fail: `getMe` returns your bot's details, `TELEGRAM_CHAT_ID` is in `.env`,
ngrok starts and shows a forwarding URL.

**Phase 2 — FastAPI gateway, local uvicorn, real Telegram messages**

Write all gateway code. Run with uvicorn directly — no Docker. Use ngrok to
expose localhost to Telegram. Validate the full flow with real messages from your
phone. Google credentials are read from disk as in Stage 1d.

Pass/fail: real Telegram messages produce real replies, tasks and events appear
in Google, logs show correct agent behaviour.

**Phase 3 — Dockerise, credential volume mount, same Telegram flow**

Package the working gateway into a Docker image. Run it locally with a credential
volume mount. Re-register the ngrok webhook to the Docker port. Validate the same
Telegram flow works identically inside the container.

Pass/fail: all Phase 2 smoke tests pass with the app running inside Docker.

**Phase 4 — Deploy (deferred)**

By this point you have a fully tested Docker image. The hosting decision is made
separately. A deployment appendix will cover the chosen provider's specific
requirements (HTTPS, credential storage, process supervision).

---

## 9. Project Structure — Stage 2 Changes

Only new and modified files are listed.

```
project/
├── gateway/
│   ├── __init__.py              # NEW — empty
│   ├── app.py                   # NEW — FastAPI app, lifespan, webhook endpoint
│   └── telegram_client.py       # NEW — Telegram Bot API send helper
│
├── Dockerfile                   # NEW — container image definition
├── .dockerignore                # NEW — excludes secrets and caches from image
├── requirements.txt             # UPDATED — fastapi, uvicorn, httpx added
└── .env                         # UPDATED — TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
                                 #           WEBHOOK_SECRET added
```

Note: no `startup.py` this stage. Credential writing is not needed while
credentials are available on disk (Phase 2) or via volume mount (Phase 3).

---

## 10. Updated `requirements.txt`

```
# Stage 1a
pydantic-ai
python-dotenv

# Stage 1a-1d
aiosqlite
colorlog

# Stage 2
fastapi
uvicorn[standard]
httpx
```

`httpx` is used for outbound Telegram API calls. No heavy Telegram bot framework
is needed — the Bot API is a simple REST interface and `httpx` handles it cleanly.

---

## 11. Updated `.env`

```dotenv
# Stage 1a
LLM_MODEL=openrouter/nvidia/nemotron-4-340b-instruct

# Stage 1b / 1c
GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
USER_GOOGLE_EMAIL=your-email@gmail.com
USER_ID=local_user
SQLITE_PATH=data/assistant.db
LOG_FILE=logs/assistant.log
LOG_LEVEL=INFO

# Stage 2
# LLM Provider
LLM_ORGANIZATION=openrouter
SUPERVISOR_MODEL=mistralai/mistral-small-3.2-24b-instruct
SPECIALIST_MODEL=mistralai/ministral-8b-2512
OPENROUTER_API_KEY=
APP_NAME=closed-claw

# Paths
LOG_FILE=logs/assistant.log
LOG_LEVEL=INFO
MEMORY_DIR=memory/

# Database
SQLITE_PATH=data/assistant.db

# Google services
GOOGLE_OAUTH_CLIENT_ID=
GOOGLE_OAUTH_CLIENT_SECRET=
USER_GOOGLE_EMAIL=

# Telegram
TELEGRAM_BOT_TOKEN=7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TELEGRAM_CHAT_ID=123456789
WEBHOOK_SECRET=<generate: python -c "import secrets; print(secrets.token_hex(32))">
```

`WEBHOOK_SECRET` is a random hex token appended to the webhook URL. Generate it
once and keep it identical across all environments — local, Docker, and any future
hosting provider.

---

## 12. Telegram Bot Setup

### What is BotFather?

BotFather is Telegram's official bot management bot. You create and configure all
bots through it — there is no web dashboard. Everything is done by chatting with
`@BotFather` in Telegram.

### Creating your bot

1. Open Telegram, search for `@BotFather`, tap **Start**
2. Send `/newbot`
3. BotFather asks for a **display name** (e.g. `My Assistant`) — shown in the chat header
4. BotFather asks for a **username** ending in `bot` (e.g. `myassistant_bot`) — used to find the bot
5. BotFather replies with your bot token:
   ```
   7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
6. Add to `.env`:
   ```dotenv
   TELEGRAM_BOT_TOKEN=7123456789:AAFxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
7. Verify the token works — paste in your browser:
   ```
   https://api.telegram.org/bot<TOKEN>/getMe
   ```
   Expected: `{"ok": true, ...}` with your bot's username and details.
   If you see an error, the token was copied incorrectly — go back to BotFather.

> [!WARNING] The word `bot` must be included and must directly precede the token
> in all Telegram API URLs: `https://api.telegram.org/bot<TOKEN>/...`

### Getting your chat_id

Your `TELEGRAM_CHAT_ID` is your personal Telegram user ID. It is used as the
allowlist — only messages from this chat_id are processed by the agent.

1. Check no webhook is already registered — paste in your browser:
   ```
   https://api.telegram.org/bot<TOKEN>/getWebhookInfo
   ```
   If `"url"` is not empty, clear it:
   ```
   https://api.telegram.org/bot<TOKEN>/deleteWebhook
   ```
   Expected after clearing: `{"url": "", ...}`

2. Open Telegram, find your bot by username, send any message (e.g. `hello`)

3. Immediately call `getUpdates` in your browser:
   ```
   https://api.telegram.org/bot<TOKEN>/getUpdates
   ```

4. Find `chat.id` in the response — that is your chat_id:
   ```json
   {
       "ok": true,
       "result": [{
           "update_id": 519312100,
           "message": {
               "from": { "id": 123456789, "first_name": "roy", "username": "..." },
               "chat": { "id": 123456789, "type": "private" },
               "text": "hello"
           }
       }]
   }
   ```

   > [!NOTE] `from.id` and `chat.id` are identical for private conversations.
   > Either value is correct — use `chat.id`.

5. If `getUpdates` returns an empty `result` array:
   - A webhook was previously registered and Telegram has stopped buffering updates
   - Go back to Step 1, clear the webhook with `deleteWebhook`
   - Send a fresh message to your bot and call `getUpdates` again immediately

6. Add to `.env`:
   ```dotenv
   TELEGRAM_CHAT_ID=123456789
   ```

### Webhook secret

When you register your webhook URL with Telegram, that URL becomes public —
anyone who discovers it could send fake requests to your bot pretending to be
Telegram. The webhook secret prevents this.

It works like a password between Telegram and your server:

1. You generate a random secret string
2. You give it to Telegram when registering the webhook
3. Telegram includes it in every request it sends you, in the
   `X-Telegram-Bot-Api-Secret-Token` header
4. Your handler checks that header on every incoming request — if it is missing
   or wrong, the request is rejected immediately with 403

Without this, anyone who finds your ngrok or production URL can send arbitrary
messages to your bot and trigger your agent loop.

The secret must be 1–256 characters, only `A-Z`, `a-z`, `0-9`, `_`, and `-`.
`secrets.token_hex(32)` generates a cryptographically random 64-character hex
string that satisfies this requirement:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

Add the output to `.env`:

```dotenv
WEBHOOK_SECRET=<paste output here>
```

Keep this value constant — changing it requires re-registering the webhook with
Telegram.

### Registering the webhook

You register the webhook URL with Telegram once ngrok is running (Phase 2) or
when you have a production URL (Phase 4). The URL format is:

```
https://<your-public-url>/webhook/<WEBHOOK_SECRET>
```

Registration command (PowerShell):

```powershell
$TOKEN  = $env:TELEGRAM_BOT_TOKEN
$NGROK  = "https://a1b2c3d4.ngrok-free.app"   # your current ngrok URL
$SECRET = $env:WEBHOOK_SECRET

Invoke-WebRequest -Uri "https://api.telegram.org/bot$TOKEN/setWebhook" `
    -Method POST `
    -ContentType "application/json" `
    -Body (@{
        url             = "$NGROK/webhook/$SECRET"
        allowed_updates = @("message")
    } | ConvertTo-Json)
```

Expected response:

```json
{"ok": true, "result": true, "description": "Webhook was set"}
```

Verify registration:

```powershell
Invoke-WebRequest -Uri "https://api.telegram.org/bot$TOKEN/getWebhookInfo" |
    Select-Object -ExpandProperty Content
```

Expected: `"url"` matches your ngrok URL, `"pending_update_count"` is 0.

> [!NOTE] Re-register the webhook every time your public URL changes — on every
> ngrok restart (free tier) or when switching from ngrok to a production domain.
> On a stable production domain, register once and never again.

---

## 13. ngrok

### What is ngrok?

ngrok is a tunnelling tool. It creates a secure public HTTPS URL that forwards
all traffic to a port on your local machine. From the outside world it looks like
a real server — but every request is transparently forwarded to your `localhost`.

Without ngrok, Telegram cannot reach your bot during development because:

- Your machine has no public IP address
- Your router blocks inbound connections
- Telegram requires HTTPS, which `localhost` does not have

With ngrok running, the flow becomes:

```
Telegram → https://<random-id>.ngrok.io/webhook/<secret> → localhost:8000/webhook/<secret>
```

Your FastAPI app never knows the difference — it just sees a normal HTTP request
arriving on port 8000.

### What ngrok is not

ngrok is not a production hosting solution. It is a development tool only. The
free tier gives you a different random URL every time you restart it, which means
re-registering your Telegram webhook each session. For production, you deploy to
a real server with a fixed domain and ngrok is no longer needed.

### Install

```powershell
winget install ngrok
```

Or download from https://ngrok.com/download.

Create a free account at https://ngrok.com, then connect your auth token:

```powershell
ngrok config add-authtoken <YOUR_NGROK_TOKEN>
```

The auth token is required even for the free tier. Without it, tunnels expire
after 1 hour and show an interstitial warning page to visitors.

### Starting the tunnel

```powershell
ngrok http 8000
```

ngrok displays:

```
Forwarding  https://a1b2c3d4.ngrok-free.app -> http://localhost:8000
```

Copy the `https://` URL — this is your public webhook base URL. Use it in the
`setWebhook` registration command from Section 12.

---

## 14. `gateway/telegram_client.py`

Thin wrapper around the Telegram Bot API `sendMessage` endpoint. Uses `httpx`
directly — no heavy bot framework needed for outbound sends. The token is read
from the environment at module load time and reused across all calls.

Telegram enforces a hard 4096-character limit on messages. Messages exceeding
this are truncated with a notice rather than crashing — a long agent response
is better delivered truncated than not at all.

```python
from __future__ import annotations

import os

import httpx

from core.logger import logger

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
_BASE = f"https://api.telegram.org/bot{_TOKEN}"


async def send_message(chat_id: int, text: str) -> None:
    """Send a plain-text message to a Telegram chat.

    Telegram enforces a 4096-character message limit. Messages exceeding this
    are truncated with a notice rather than crashing.
    """
    if len(text) > 4096:
        text = text[:4050] + "\n\n[message truncated]"

    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{_BASE}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )

    if response.status_code != 200:
        logger.error(
            "telegram_client.send_message | FAILED | status=%d | body=%s",
            response.status_code, response.text,
        )
    else:
        logger.debug("telegram_client.send_message | ok | chat_id=%d", chat_id)
```

---

## 15. `gateway/app.py`

The FastAPI application. Two endpoints: `GET /health` and `POST /webhook/{secret}`.

### 15.1 Lifespan

The lifespan handler runs once at startup — not per request. It initialises the
`SupervisorAgent` and `SQLiteStore` and stores them as module-level globals. This
means the Supervisor's conversation history persists across all requests in the
same process lifetime, which is the correct behaviour for a stateful assistant.

Failing fast in lifespan (raising `RuntimeError` on missing config) is intentional.
A misconfigured gateway should crash immediately with a clear error rather than
silently processing messages that cannot succeed.

### 15.2 Webhook handler

#### What is a webhook?

A webhook is the reverse of a normal API call. Normally your code calls an
external service ("give me new messages"). With a webhook, the external service
calls you ("here is a new message, right now"). Telegram uses webhooks to deliver
messages to your bot instantly — no polling, no delay.

How it works in practice:

1. You register a URL with Telegram: "send all messages for my bot to this address"
2. A user sends your bot a message on Telegram
3. Telegram immediately makes an HTTPS POST to your URL with the message as JSON
4. Your server processes it and returns `200 OK`
5. Telegram considers the message delivered

If your server returns anything other than `200 OK`, or takes longer than 30
seconds, Telegram retries delivery for up to 24 hours. This is why the handler
always returns `{"ok": True}` — even for messages it ignores (wrong chat_id,
edits, reactions) — so Telegram never retries unnecessarily.

#### Handler sequence

1. **Validate secret** — reject unknown callers with 403 immediately
2. **Extract message** — return 200 silently for non-message updates (edits,
   reactions, etc.) so Telegram does not retry them
3. **Validate chat_id** — return 200 silently for unknown senders, log a warning
4. **Handle commands** — `/start` gets a canned response, other commands ignored
5. **Run agent loop** — synchronous in Stage 2; Stage 3 moves this to a queue
6. **Reply** — send the Supervisor's message back to Telegram
7. **Write turn** — append the exchange to SQLite

The handler always returns `{"ok": True}` for non-403 responses. This is
required — Telegram retries any non-200 response for up to 24 hours.

```python
from __future__ import annotations

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request

from agents.supervisor import SupervisorAgent
from core.deps import AgentDeps
from core.logger import logger
from gateway.telegram_client import send_message
from memory.sqlite_store import SQLiteStore
from schemas.turn_record import TurnRecord

# ── environment ───────────────────────────────────────────────────────────────

_WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
_ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
_USER_ID = os.getenv("USER_ID", "local_user")
_USER_EMAIL = os.getenv("USER_GOOGLE_EMAIL", "")
_LLM_MODEL = os.getenv("LLM_MODEL", "")

# ── application state ─────────────────────────────────────────────────────────

_supervisor: SupervisorAgent
_store: SQLiteStore


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic.

    Runs once when the process starts. Validates required config, initialises
    the SQLite store, and builds the SupervisorAgent. All three are reused
    across every request — not rebuilt per message.

    Raises RuntimeError on missing config so the process fails fast with a
    clear error rather than silently mishandling messages.
    """
    global _supervisor, _store

    if not _USER_EMAIL:
        raise RuntimeError("USER_GOOGLE_EMAIL is not set")
    if not _WEBHOOK_SECRET:
        raise RuntimeError("WEBHOOK_SECRET is not set")
    if not _ALLOWED_CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is not set")

    _store = SQLiteStore()
    await _store.initialise()

    _supervisor = SupervisorAgent()

    logger.info(
        "gateway | started | user=%s | email=%s | allowed_chat_id=%d",
        _USER_ID, _USER_EMAIL, _ALLOWED_CHAT_ID,
    )
    yield
    logger.info("gateway | shutdown")


app = FastAPI(lifespan=lifespan)


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    """Health check endpoint. Returns 200 when the gateway is ready."""
    return {"status": "ok"}


# ── webhook ───────────────────────────────────────────────────────────────────

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request) -> dict:
    """Receive a Telegram Update and process it.

    Always returns 200 for non-403 responses — even for ignored messages —
    so Telegram does not retry. Telegram retries delivery on any non-200
    response for up to 24 hours.
    """
    # 1. Validate secret
    if secret != _WEBHOOK_SECRET:
        logger.warning("webhook | invalid secret | received=%r", secret)
        raise HTTPException(status_code=403, detail="Forbidden")

    update = await request.json()
    logger.debug("webhook | update=%r", update)

    # 2. Extract message — ignore edits, reactions, and other non-message updates
    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id: int = message.get("chat", {}).get("id", 0)
    text: str = message.get("text", "").strip()

    # 3. Allowlist check — only your chat_id is permitted this stage
    if chat_id != _ALLOWED_CHAT_ID:
        logger.warning("webhook | unauthorised chat_id=%d | ignoring", chat_id)
        return {"ok": True}

    # 4. Handle commands; ignore empty messages
    if not text:
        return {"ok": True}
    if text.startswith("/"):
        if text == "/start":
            await send_message(chat_id, "Assistant ready. Send me a message.")
        return {"ok": True}

    logger.info("webhook | chat_id=%d | text=%r", chat_id, text)

    # 5. Build deps — identity resolved here, never inside agents
    deps = AgentDeps(
        user_id=_USER_ID,
        user_email=_USER_EMAIL,
    )

    # 6. Run agent loop synchronously — Stage 3 moves this to a Redis queue
    try:
        response = await _supervisor.run(text, deps)
    except Exception:
        logger.exception("webhook | agent loop failed | chat_id=%d", chat_id)
        await send_message(chat_id, "Something went wrong. Please try again.")
        return {"ok": True}

    # 7. Reply
    await send_message(chat_id, response.message)

    # 8. Write turn record
    record = TurnRecord(
        turn_id=str(uuid.uuid4()),
        user_id=_USER_ID,
        user_email=_USER_EMAIL,
        agent_name="supervisor",
        user_input=text,
        agent_output=response.message,
        model=_LLM_MODEL,
        timestamp=datetime.now(tz=timezone.utc),
    )
    await _store.write_turn(record)

    return {"ok": True}
```

---

## 16. `Dockerfile` and `.dockerignore`

### What is Docker and why is it used here?

Docker packages your application and everything it needs (Python version,
dependencies, file structure) into a single portable unit called an **image**.
Running that image creates a **container** — an isolated process that behaves
identically on your laptop, a colleague's machine, or any cloud server.

Without Docker, deploying means manually installing Python, recreating your
virtualenv, and hoping the server environment matches your local one. With Docker,
you ship the environment itself.

Three concepts to know:

- **Image** — the blueprint, built from your `Dockerfile`. Read-only. Built once,
  run anywhere.
- **Container** — a running instance of an image. You can run many containers from
  the same image.
- **Docker Desktop** — the GUI application that runs the Docker engine on Windows.
  Must be running before any `docker` commands work.

### Prerequisites

Install Docker Desktop from https://www.docker.com/products/docker-desktop and
start it. Confirm it is running:

```powershell
docker version
```

Expected: client and server version numbers printed. If you see "Cannot connect
to the Docker daemon", Docker Desktop is not running — open it from the Start menu
and wait for the whale icon in the taskbar to stop animating.

### The `Dockerfile`

The image is built from `python:3.12-slim` to keep size minimal. `uv` is
installed so `uvx` is available at runtime — `workspace-mcp` is fetched and
cached via `uvx` on first use. `curl` is included for health check debugging.

Credentials are NOT copied into the image. They are provided at runtime via
a volume mount (Phase 3) or host-specific mechanism (Phase 4+). Baking
credentials into an image is a security risk and makes rotation impossible
without a rebuild.

```dockerfile
FROM python:3.12-slim

# curl for healthcheck debugging inside the container
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv provides uvx, which fetches and runs workspace-mcp at runtime
RUN pip install uv --no-cache-dir

WORKDIR /app

# Install dependencies first — cached layer, only rebuilt when requirements change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 10000

# PORT env var allows the host to override the port without rebuilding the image
CMD ["sh", "-c", "uvicorn gateway.app:app --host 0.0.0.0 --port ${PORT:-10000}"]
```

### `.dockerignore`

Prevents secrets, local data, caches, and development artefacts from being
copied into the image. `.env` must never be in the image — environment variables
are passed at runtime via `--env-file` or the host's secrets mechanism.

`memory/` is intentionally NOT excluded — it contains agent persona and brain
files that are part of the application, not secrets.

```
.env
.env.*
__pycache__/
*.pyc
*.pyo
.pytest_cache/
*.egg-info/
.git/
.gitignore
data/
logs/
*.log
*.db
tests/
```

### Building the image

```powershell
docker build -t closed-claw .
```

Docker reads your `Dockerfile` top to bottom, executes each instruction as a
layer, and produces a tagged image called `closed-claw`. The first build
downloads the base image and installs all dependencies — expect 3–5 minutes.
Subsequent builds are fast because unchanged layers are cached.

Expected final line:

```
=> => naming to docker.io/library/closed-claw
```

### Running the container

```powershell
docker run `
    --env-file .env `
    -p 10000:10000 `
    -v "$env:APPDATA\workspace-mcp\credentials:/root/.local/share/workspace-mcp/credentials:ro" `
    closed-claw
```

### Rebuilding after code changes

Every time you change Python code, rebuild the image and restart:

```powershell
docker ps                          # find the container ID
docker stop <container-id>

docker build -t closed-claw .
docker run `
    --env-file .env `
    -p 10000:10000 `
    -v "$env:APPDATA\workspace-mcp\credentials:/root/.local/share/workspace-mcp/credentials:ro" `
    closed-claw
```

Because dependency layers are cached, rebuilds after code-only changes (no
`requirements.txt` change) take under 30 seconds.

### Viewing container logs

```powershell
docker ps                          # get container ID
docker logs <container-id>         # print all logs
docker logs -f <container-id>      # follow logs in real time
```

### Useful Docker commands

| Command | Purpose |
|---|---|
| `docker ps` | List running containers |
| `docker ps -a` | List all containers including stopped |
| `docker images` | List all local images |
| `docker stop <id>` | Stop a running container |
| `docker rm <id>` | Delete a stopped container |
| `docker rmi closed-claw` | Delete the image (forces full rebuild next time) |
| `docker system prune` | Clean up all stopped containers and dangling images |

### When `requirements.txt` changes

If you add a new dependency, the pip install layer is invalidated and Docker
reinstalls everything from that point. This is expected — just run
`docker build -t closed-claw .` again.

---

## 17. Implementation Sequence
The sequence is strictly ordered. Each phase has a clear pass/fail check.
Do not proceed to the next phase until the current one passes.


### PHASE 1 — Telegram bot and tooling setup
---
Before writing any code, set up the Telegram bot and install ngrok.
Full details in Sections 12 and 13.

#### **Step 1** — Branch

```powershell
git checkout main
git pull
git checkout -b stage/2
```

#### **Step 2** — Create Telegram bot and get credentials
See **Section 12 — Creating your bot** and **Getting your chat_id**.

Done when: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` are in `.env`.

#### **Step 3** — Generate webhook secret
See **Section 12 — Webhook secret**.

Done when: `WEBHOOK_SECRET` is in `.env`.

#### **Step 4** — Install ngrok

See **Section 13**.

Done when: `ngrok http 8000` starts and shows a forwarding URL.

**Phase 1 complete when:** All three values (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`,
`WEBHOOK_SECRET`) are in `.env` and ngrok is confirmed working.


### PHASE 2 — Gateway code + local uvicorn
---

#### **Step 5** — Install new dependencies

```powershell
pip install fastapi uvicorn[standard] httpx
```

Update `requirements.txt` from Section 10.

#### **Step 6** — Create `gateway/` package

```powershell
New-Item -ItemType Directory -Name gateway
New-Item gateway/__init__.py
```

#### **Step 7** — Implement `gateway/telegram_client.py`

Implement from Section 14. Verify:

```powershell
python -c "from gateway.telegram_client import send_message; print('telegram_client OK')"
```

#### **Step 8** — Implement `gateway/app.py`

Implement from Section 15. Verify:

```powershell
python -c "from gateway.app import app; print('app OK')"
```

#### **Step 9** — Start uvicorn

```powershell
uvicorn gateway.app:app --host 0.0.0.0 --port 8000 --reload
```

Expected log output:

```
gateway | started | user=local_user | email=your@gmail.com | allowed_chat_id=123456789
INFO:     Application startup complete.
```

If you see a `RuntimeError`, check that all three required env vars are set:
`USER_GOOGLE_EMAIL`, `WEBHOOK_SECRET`, `TELEGRAM_CHAT_ID`.

Verify health:

```powershell
curl http://localhost:8000/health
```

Expected: `{"status":"ok"}`

#### **Step 10** — Test agent loop with fake webhook

Before connecting Telegram, verify the agent loop works via a fake POST.
This isolates gateway bugs from Telegram wiring bugs.

```powershell
$SECRET  = $env:WEBHOOK_SECRET
$CHAT_ID = [int]$env:TELEGRAM_CHAT_ID

$body = @{
    update_id = 1
    message   = @{
        message_id = 1
        chat       = @{ id = $CHAT_ID; type = "private" }
        text       = "What can you help me with?"
        date       = 1700000000
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:8000/webhook/$SECRET" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
```

Expected:
- Response `{"ok":true}`
- uvicorn logs show the Supervisor ran
- `delegate_to_specialists` NOT called for a general question
- `SupervisorAgent.usage` log line appears

#### **Step 11** — Start ngrok tunnel

In a second terminal (see Section 13):

```powershell
ngrok http 8000
```

Copy the `https://` forwarding URL.

---

#### **Step 12** — Register Telegram webhook

See **Section 12 — Registering the webhook** for full command.

Replace the ngrok URL placeholder with your current forwarding URL and run.

Expected: `{"ok": true, "result": true, "description": "Webhook was set"}`

#### **Step 13** — Smoke test: real Telegram messages

Open Telegram and send the following to your bot. Check uvicorn logs after each.

| Message | Expected behaviour |
|---|---|
| `What can you help me with?` | Direct reply, no tool call in logs |
| `Add a task called Review report due this Friday` | Task + calendar event created |
| `Send an email to your@gmail.com subject Stage 2 test body This is a test` | Email delivered |
| `Send an email to John` | Bot asks for John's email address |
| `Add task called Prepare slides due Monday and email me a reminder` | Both actions in one reply |
| `/start` | `Assistant ready. Send me a message.` |

Also send a message from a different Telegram account. Expected: no reply, log shows:

```
webhook | unauthorised chat_id=987654321 | ignoring
```

**Phase 2 complete when:** All rows above behave as expected with real Telegram
messages through ngrok.

### PHASE 3 — Docker
---

#### **Step 14** — Ensure Docker Desktop is running
See `Section 16 — Prerequisites`.

```powershell
docker version
```

Expected: client and server version numbers.

#### **Step 15** — Create `Dockerfile` and `.dockerignore`

Implement both from Section 16.

#### **Step 16** — Build the Docker image

```powershell
docker build -t closed-claw .
```

Expected final line:

```
=> => naming to docker.io/library/closed-claw
```

If the build fails at `pip install`, run with `--no-cache` to rule out a stale layer:

```powershell
docker build --no-cache -t closed-claw .
```

#### **Step 17** — Run the Docker container

See **Section 16 — Running the container** for the full command with credential
volume mount explained.

```powershell
docker run `
    --env-file .env `
    -p 10000:10000 `
    -v "$env:APPDATA\workspace-mcp\credentials:/root/.local/share/workspace-mcp/credentials:ro" `
    closed-claw
```

Expected log output:

```
gateway | started | user=local_user | email=your@gmail.com | allowed_chat_id=123456789
INFO:     Application startup complete.
```

Verify health:

```powershell
curl http://localhost:10000/health
```

Expected: `{"status":"ok"}`

#### Step 18 — Re-register Telegram webhook to Docker port

Stop the current ngrok session and start a new one pointing to port 10000:

```powershell
ngrok http 10000
```

Copy the new `https://` URL and re-register the webhook using the command from
Section 12, replacing the ngrok URL.

---

#### **Step 19** — Smoke test inside Docker

Repeat the same Telegram message tests from Step 13. All should behave
identically — the only difference is the app is now running inside Docker.

Check Docker logs in real time:

```powershell
docker logs -f <container-id>
```

**Phase 3 complete when:** All smoke tests from Step 13 pass with the app running
inside Docker with the credential volume mount.

---

### PHASE 4 — Deploy (deferred)

By this point you have a fully tested Docker image that runs identically in all
local environments. The hosting decision is made based on your requirements.

| Option | HTTPS | Persistent filesystem | Cost | Notes |
|---|---|---|---|---|
| Render free | Automatic | No | Free | Cold starts; credential workaround needed |
| Render Starter | Automatic | No | $7/mo | No cold starts; credential workaround needed |
| DigitalOcean Droplet | Manual (Caddy) | Yes | ~$6/mo | Volume mount works directly |
| Hetzner VPS | Manual (Caddy) | Yes | ~$4/mo | Cheapest; same setup as DigitalOcean |
| Home server | Manual | Yes | Electricity | Requires static IP or dynamic DNS |

For hosts with a **persistent filesystem** (DigitalOcean, Hetzner, home server):
copy your credential file to the server and use the same volume mount from
Phase 3. No changes to the image or code required.

For hosts with an **ephemeral filesystem** (Render): the credential must be
base64-encoded and written to disk at container startup. This is covered in a
dedicated deployment appendix written when you make that choice.

The deployment step is NOT part of Stage 2 scope.

---

## 18. Troubleshooting

**Bot does not reply at all**
Check uvicorn or Docker logs for incoming webhook POSTs. If no POST appears:
- Confirm ngrok is running and showing a forwarding URL
- Re-register the webhook — the ngrok URL may have changed since last registration
- Run `getWebhookInfo` and confirm the URL ends with `/webhook/<your-secret>`

**Bot replies "Something went wrong"**
The agent loop raised an exception. Check logs for the full traceback. Most
common causes: `USER_GOOGLE_EMAIL` not set, MCP subprocess failed to start,
`workspace-mcp` credential not found.

**Webhook returns 403**
The `WEBHOOK_SECRET` in the `setWebhook` URL does not match `WEBHOOK_SECRET`
in `.env`. They must be character-for-character identical.

**`workspace-mcp` slow on first tool call inside Docker**
`uvx` fetches `workspace-mcp` on first use and caches it inside the container.
The first MCP tool call in a fresh container may take 10–20 seconds while this
download happens. Subsequent calls in the same container are fast. This is a
known limitation addressed in Stage 3 with a persistent MCP server.

**Credential not found inside Docker**
Confirm the volume mount path is correct. Verify the file exists inside the
container:

```powershell
docker exec <container-id> ls /root/.local/share/workspace-mcp/credentials/
```

The filename must match your `USER_GOOGLE_EMAIL` exactly.

**ngrok URL changed**
Free ngrok generates a new URL on every restart. Re-register the Telegram webhook
using the command from Section 12 with the new URL after every ngrok restart.

**Messages from another chat_id are processed**
Confirm `TELEGRAM_CHAT_ID` in `.env` is set to an integer, not a string with
quotes. Check logs for `webhook | unauthorised chat_id=...` to confirm the
allowlist check is running.

**`getUpdates` returns empty result**
Send a message to your bot first, then call `getUpdates`. Telegram only stores
recent updates and clears them once a webhook is registered — use `getUpdates`
only before webhook registration.

---

## 19. How Stage 3 Builds on This

Stage 2 processes requests synchronously — the webhook handler awaits the full
agent run before returning 200. This is acceptable for single-user use but has
two problems at scale:

- Telegram's 30-second timeout can be hit on slow LLM or MCP responses
- Multiple concurrent users block each other in the same process

Stage 3 introduces:

- **Redis queue** — the webhook handler enqueues the message and returns 200
  immediately. A worker coroutine drains the queue, runs the agent loop, and
  sends the reply asynchronously. Telegram's timeout is never a concern.
- **PostgreSQL** — replaces ephemeral SQLite with a persistent managed database
  that survives container restarts and redeploys.
- **Persistent MCP server** — Stage 1d introduced `mcps/mcp_pool.py` with
  `get_pool_server()` as the foundation. Stage 3 promotes this to a process-level
  singleton: `workspace-mcp` started once at app startup in the lifespan handler
  and shared across all requests. Eliminates the per-request cold start that
  currently adds 10–20 seconds to the first tool call.
- **Memory** — `markdown_store.py` loads persona files from `memory/agents/` and
  user facts from `memory/brain/` into agent system prompts at startup.
- **Multi-user OAuth** — when a new `chat_id` messages the bot, the gateway sends
  a Google auth URL. The callback endpoint exchanges the code for a token and
  saves the credential for that user.

None of the agent code changes in Stage 3. Only the gateway and infrastructure
layer change — exactly as Stage 2 did not change Stage 1d's agents.

### 19.1 Specialist Skills

Each specialist agent's behavioural instructions currently live inside
`_build_system_prompt()` in Python code. This is fine while the instructions
are short. As the assistant matures — handling edge cases, learning personal
preferences, following formatting rules — those instructions will grow. Editing
agent behaviour will require a code change, a commit, and a redeploy.

Skills decouple behavioural instructions from agent mechanics. Behaviour lives
in an editable markdown file. The agent file stays thin and stable.

This is the same pattern OpenClaw uses: at startup each agent scans a skills
folder, injects only names and one-line descriptions into the system prompt, and
reads the full instruction file on demand only when the skill is relevant. Full
instructions are never loaded unless needed — token cost stays low.

- **Specialist Skills** — Stage 1d defined the target structure (Stage 3+): each
  specialist agent loads behavioural instructions from `skills/<key>/SKILL.md` at
  startup, injecting them into `_build_system_prompt()`. The skill file is plain
  markdown, editable without a code change or redeploy. Implement when any
  specialist's `_build_system_prompt()` exceeds ~30 lines of rules, or when
  Stage 3 persona and memory files (`memory/agents/`) are wired in — skills fit
  naturally as the third behavioural layer alongside those.

---

## 20. Done When

- `uvicorn gateway.app:app` starts locally and logs `gateway | started`
- `curl http://localhost:8000/health` returns `{"status":"ok"}`
- Fake webhook POST triggers the agent loop — correct log output, no crash
- ngrok tunnel active and webhook registered — `getWebhookInfo` shows correct URL
- Real Telegram messages produce real replies
- Task creation → task in Google Tasks, calendar event in Google Calendar
- Email → delivered to inbox, bot confirms
- Missing info → bot asks one question, nothing sent
- Messages from any other chat_id → silently ignored, log shows warning
- Every exchange produces a `write_turn` log line
- `/start` → `Assistant ready. Send me a message.`
- `docker build .` completes with no errors
- `docker run` with credential volume mount starts and logs `gateway | started`
- `curl http://localhost:10000/health` returns `{"status":"ok"}`
- Same Telegram flow works identically through Docker
- `python main.py` still runs the CLI loop unchanged