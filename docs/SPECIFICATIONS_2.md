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

>[!IMPORTANT] Test message from BOT
>```bash
>https://api.telegram.org/bot<TOKEN>/sendMessage?chat_id=<YOUR_CHAT_ID>&?>text=hello
>```


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


`OPTION 1`
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

`OPTION 2`
The secret must be 1–256 characters, only `A-Z`, `a-z`, `0-9`, `_`, and `-`.
`secrets.token_hex(32)` generates a cryptographically random 64-character hex
string that satisfies this requirement:


Add the output to `.env`:
```dotenv
WEBHOOK_SECRET=<paste output here>
```

Keep this value constant — changing it requires re-registering the webhook with
Telegram.

### Registering the webhook

>[!WARNING] 
> Here, we will be registering the webhook with ngrok auto generated URL. THIS IS NOT FOR PRODUCTIUON

You register the webhook URL with Telegram once ngrok is running (Phase 2) or
when you have a production URL (Phase 4). The URL format is:

```
https://<your-public-url>/webhook/<WEBHOOK_SECRET>
```

Registration command (PowerShell):
Create a new file `register_webhook.ps1` and copy the commands

```text
$TOKEN="<<TELEGRAM_BOT_TOKEN>>"
$NGROK="https://a1b2c3d4.ngrok-free.app"   # your current ngrok URL
$SECRET="<<WEBHOOK_SECRET>>"

Invoke-WebRequest -Uri "https://api.telegram.org/bot$TOKEN/setWebhook" `
    -Method POST `
    -ContentType "application/json" `
    -Body (@{
        url             = "$NGROK/webhook/$SECRET"
        allowed_updates = @("message")
    } | ConvertTo-Json)
```

```shell
.\register_webhook.ps1
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

>[!WARNING] Terminate WebHook
>```text
>Invoke-WebRequest -Uri "https://api.telegram.org/bot<TOKEN>/deleteWebhook??>drop_pending_updates=true" -Method POST
>```

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
winget install Ngrok.Ngrok
ngrok update
```

Or download from https://ngrok.com/download.

Create a free account at https://ngrok.com, 
Find Authtokens in the left panel, then click create "CREATE NEW AUTH TOKEN"

```powershell
ngrok config add-authtoken <YOUR_NGROK_TOKEN>
```

The auth token is required even for the free tier. Without it, tunnels expire
after 1 hour and show an interstitial warning page to visitors.

### Starting the tunnel

>[!NOTE]
>```powershell
>ngrok http 8000
>```

ngrok displays:

```
Forwarding  https://a1b2c3d4.ngrok-free.app -> http://localhost:8000
```

To test
```text
Open another terminal and run the local uvicorm on 8000
Open browser and use https://a1b2c3d4.ngrok-free.app/...... to test the basic apis
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

The handler always returns `{"ok": True}` for non-403 responses. This is
required — Telegram retries any non-200 response for up to 24 hours.

#### Why we clear pending updates on startup
Telegram buffers all messages sent to your bot while your webhook is offline. The moment your server comes back online and registers a webhook, Telegram flushes the entire buffer at once. If you sent 3 messages yesterday and 1 two days ago, all 4 arrive simultaneously the instant your gateway starts.
This causes two cascading problems:

- **Problem 1 — Concurrent agent runs**. Each buffered message spawns its own SupervisorAgent.run() call simultaneously. Your MCP subprocess is not designed for concurrent access — multiple agents competing for the same MCP connection produces unpredictable stalls and failures.
- **Problem 2 — Telegram retries compound the problem**. If those concurrent runs make your handler slow to return 200, Telegram interprets the delay as a failure and retries — adding even more concurrent runs on top of the buffered flood.

The solution is to call deleteWebhook?drop_pending_updates=true at startup, before the supervisor is initialised. Telegram discards the buffer and starts fresh. Only messages sent after your gateway is live are delivered.
This is done programmatically in the lifespan handler — not manually via PowerShell — so it happens automatically every time the gateway starts, in every environment.

#### Why we return 200 before processing (BackgroundTasks)
The agent loop — LLM call, MCP tool execution, Google API round-trips — takes several seconds. If the handler awaits the full agent run before returning, Telegram's delivery timeout can be breached. Telegram then retries, spawning a second concurrent run of the same message on top of the still-running first one.

The fix is to return 200 OK immediately and process the message in the background. FastAPI's BackgroundTasks runs the processing function after the response is already sent. Telegram gets its 200 in milliseconds and never retries.

#### Why we use an asyncio lock
Even with BackgroundTasks, two legitimate messages sent in quick succession would spawn two concurrent background tasks — two simultaneous agent runs, two concurrent MCP connections. 

The **asyncio lock _agent_lock** ensures only one agent run executes at a time. Subsequent messages queue and are processed in order.

This is the correct design for a single-user assistant. Stage 3 replaces this with a Redis queue for proper multi-user concurrency.

#### Handler sequence

1. Validate secret — reject unknown callers with 403 immediately
2. Extract message — return 200 silently for non-message updates (edits, reactions) so Telegram does not retry them
3. Validate chat_id — return 200 silently for unknown senders, log a warning
4. Handle commands — /start gets a canned response, other commands ignored
5. Return 200 immediately — Telegram is satisfied before any agent work begins
6. Background: build deps — identity resolved here, never inside agents
7. Background: run agent loop — one at a time, protected by _agent_lock
8. Background: reply — send the supervisor's response back to Telegram
9. Background: write turn — append the exchange to SQLite


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

16. Dockerfile, .dockerignore, and docker-compose.yml
What is Docker and why is it used here?
Docker packages your application and everything it needs (Python version,
dependencies, file structure) into a single portable unit called an image.
Running that image creates a container — an isolated process that behaves
identically on your laptop, a colleague's machine, or any cloud server.
Without Docker, deploying means manually installing Python, recreating your
virtualenv, and hoping the server environment matches your local one. With Docker,
you ship the environment itself.
Three concepts to know:

Image — the blueprint, built from your Dockerfile. Read-only. Built once,
run anywhere.
Container — a running instance of an image. You can run many containers from
the same image.
Docker Desktop — the GUI application that runs the Docker engine on Windows.
Must be running before any docker commands work.


What Docker Actually Does Here
When you run uvicorn gateway.app:app locally, Python finds your source files
because you are sitting in the project directory and your virtualenv has all the
packages installed. Docker replicates this environment inside an isolated container
so the same app runs identically anywhere.
The Dockerfile is a recipe that tells Docker:

Start from a clean Python 3.12 environment
Install uv (needed so uvx workspace-mcp works at runtime)
Copy your requirements.txt and install all Python packages
Copy your project source code
When the container starts, run uvicorn gateway.app:app

What is NOT in the image: your .env file and your Google OAuth credentials.
These are secrets and must never be baked in. They are provided at runtime via
docker-compose.yml.

Where workspace-mcp Stores Its Credentials
This is the most important thing to understand before mounting any volume.
workspace-mcp runs its own internal OAuth flow and saves credentials to:
/root/.google_workspace_mcp/credentials/
This is different from /root/.local/share/workspace-mcp/credentials/. The
auth_once.py script from Stage 1d saves tokens to the wrong path for Docker.
Do not use auth_once.py with Docker. Instead, let workspace-mcp do its
own auth flow the first time the container runs (see Step 18 below). After that,
the token is saved inside the container's mounted volume and survives restarts.
On your Windows machine, the equivalent path is:
C:\Users\<your-username>\.google_workspace_mcp\credentials\
Verify this folder exists and contains files after completing auth:
powershellls C:\Users\liang\.google_workspace_mcp\credentials\
You should see at minimum oauth_states.json and a token file for your account.

Where the Agent Loop Runs
The agent loop — SupervisorAgent, SpecialistAgent, workspace-mcp subprocess
— runs inside the container. When Docker starts your container it runs a real
Python process with uvicorn. That process imports gateway.app, which imports
SupervisorAgent, which imports everything else.
Your machine (Windows)
│
├── Docker container (running closed-claw image)
│   ├── uvicorn → FastAPI → SupervisorAgent → SpecialistAgent
│   │                                               │
│   │                                               └── uvx workspace-mcp (subprocess)
│   │                                                         │
│   │                                         reads/writes credentials from ──┐
│   │                                                                          │
│   └── /root/.google_workspace_mcp/credentials/  ◄── volume mount
│
└── C:\Users\liang\.google_workspace_mcp\credentials\  (on your Windows machine)

Prerequisites
Install Docker Desktop from https://www.docker.com/products/docker-desktop and
start it. The whale icon in the Windows taskbar system tray confirms it is running.
Confirm Docker is working:
powershelldocker version
Expected: both Client: and Server: sections print version numbers. If Server:
is missing, Docker Desktop is still starting — wait 30–60 seconds and retry.

The Dockerfile
Create this file at the root of your project (same level as main.py and
requirements.txt):
dockerfileFROM python:3.12-slim

# curl is useful for testing health check from inside the container
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# uv provides uvx, which fetches and runs workspace-mcp at runtime
RUN pip install uv --no-cache-dir

WORKDIR /app

# Install dependencies first — this layer is cached and only rebuilds
# when requirements.txt changes, not on every code change
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project source code into /app inside the image
COPY . .

EXPOSE 10000

# PORT env var lets the host override the port without rebuilding
CMD ["sh", "-c", "uvicorn gateway.app:app --host 0.0.0.0 --port ${PORT:-10000}"]
Why WORKDIR /app? This sets the working directory inside the container. When
uvicorn starts, Python's module resolution starts from /app. Since your code is
copied to /app, imports like from agents.supervisor import SupervisorAgent
resolve correctly.
Why --host 0.0.0.0? By default uvicorn binds to 127.0.0.1 (loopback only).
Inside Docker, that means "inside the container" — your host machine cannot reach
it. 0.0.0.0 accepts connections on all interfaces, allowing Docker's port
mapping to work.
Why COPY requirements.txt before COPY . .? Docker builds in layers and caches
each one. If you copy requirements.txt separately, Docker only re-runs
pip install when requirements.txt actually changes. A code-only change skips
that layer entirely — rebuilds take seconds instead of minutes.

The .dockerignore
Create this file at the root of your project:
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
Why .env is excluded: your secrets (API keys, tokens) must never be baked into
the image. They are passed at runtime via docker-compose.yml.
Why data/ and logs/ are excluded: these contain runtime-generated files
(SQLite database, log files) that have no place in the image.
Why memory/ is NOT excluded: memory/agents/ and memory/brain/ contain
persona and instruction files that are part of your application code. They belong
in the image.

Getting requirements.txt
powershellpip freeze > requirements.txt

WARNING — Windows only: In requirements.txt, pywin32 must have a
platform guard or the Docker build will fail. Find the line and change it to:
pywin32==311; sys_platform == 'win32'
This tells pip to skip pywin32 on Linux (inside Docker) while keeping it
on Windows for local development.


The docker-compose.yml
docker-compose.yml replaces all manual docker build and docker run commands.
It defines the image, container name, restart policy, ports, environment, and
volume mounts in one file. You run it once and Docker handles everything from
that point forward — including auto-starting the container when Docker Desktop
starts after a PC restart.
Create this file at the root of your project:
yamlservices:
  closed-claw:
    build: .
    container_name: closed-claw-dev
    restart: unless-stopped
    env_file: .env
    ports:
      - "10000:10000"
    volumes:
      - C:/Users/liang/.google_workspace_mcp/credentials:/root/.google_workspace_mcp/credentials

Replace liang with your actual Windows username.

Key fields explained:
build: . — builds the image from the Dockerfile in the current directory.
No separate docker build command needed.
container_name: closed-claw-dev — gives the container a fixed name so you can
reference it in logs and exec commands.
restart: unless-stopped — Docker automatically restarts the container if it
crashes or if Docker Desktop restarts after a PC reboot. You never need to
manually start it again after the first run.
env_file: .env — injects all variables from .env into the container at
runtime. Secrets are never baked into the image.
ports: "10000:10000" — maps port 10000 on your Windows machine to port 10000
inside the container. http://localhost:10000/docs reaches uvicorn inside Docker.
volumes — mounts the workspace-mcp credential folder from your Windows
machine into the container at the exact path workspace-mcp expects. The
container reads and writes tokens here. Because it is a bind mount (not :ro),
workspace-mcp can write refreshed tokens back to disk — required for the OAuth
token refresh to work correctly.

First-Time Google OAuth Inside Docker
workspace-mcp runs its own OAuth server on port 8000 inside the container. The
first time it tries to access Google Tasks, Calendar, or Gmail, it starts this
server and generates an authorization URL.
To complete the OAuth flow from inside Docker, you need to temporarily expose port
8000 so the Google callback can reach the container. Do this once only:
Step A — Add port 8000 temporarily to docker-compose.yml:
yamlports:
  - "10000:10000"
  - "8000:8000"
Step B — Start the container:
powershelldocker compose up -d
Step C — Trigger a Google tool call by sending any message that uses Tasks,
Calendar, or Gmail. Check the logs:
powershelldocker compose logs -f
You will see an authorization URL printed in the logs:
Authorization URL: https://accounts.google.com/o/oauth2/auth?...&redirect_uri=http://localhost:8000/oauth2callback&...
Step D — Copy that full URL and open it in your browser. Log in with your
Google account and approve all permissions.
Step E — Google redirects to http://localhost:8000/oauth2callback. Because
port 8000 is exposed, this reaches the container. workspace-mcp exchanges the
code for a token and saves it to the mounted volume at:
C:\Users\liang\.google_workspace_mcp\credentials\
Step F — Verify the token was saved on your Windows machine:
powershellls C:\Users\liang\.google_workspace_mcp\credentials\
You should see a token file for your Google account.
Step G — Remove the temporary port 8000 exposure from docker-compose.yml.
Your final docker-compose.yml should only expose port 10000:
yamlports:
  - "10000:10000"
Restart to apply:
powershelldocker compose down
docker compose up -d
From this point on, workspace-mcp reads the saved token on every request and
refreshes it automatically. You never need to re-authenticate unless you revoke
access in your Google account settings.

Starting and Managing the Container
First time (or after any code change):
powershelldocker compose up -d --build
This builds the image and starts the container in one command. The -d flag runs
it in the background. Your terminal is free immediately.
Every subsequent start (no code change):
powershelldocker compose up -d
After a PC restart with Docker Desktop set to auto-start, the container starts
automatically — you do not need to run any command at all.
Follow logs:
powershelldocker compose logs -f
Stop the container:
powershelldocker compose down
After code changes — rebuild and restart:
powershelldocker compose up -d --build
Docker only rebuilds layers that changed. A code-only change (no requirements.txt
change) takes under 30 seconds.

What to Expect When the Container Starts
gateway | started | user=local_user | email=your@gmail.com | allowed_chat_id=123456789
INFO:     Started server process [1]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:10000 (Press CTRL+C to quit)
If you see RuntimeError about missing env vars, check .env — one of
USER_GOOGLE_EMAIL, WEBHOOK_SECRET, or TELEGRAM_CHAT_ID is missing.

Verifying the Container in Docker Desktop
Open Docker Desktop → Containers. You will see closed-claw-dev listed with
a green dot (running). Click the container name to see live logs, environment
variables, and resource usage. The stop/restart buttons are in the Actions column.
Open Docker Desktop → Images. You will see closed-claw listed with its size
and creation time.

Useful Commands Reference
CommandPurposedocker compose up -d --buildBuild image and start containerdocker compose up -dStart container (no rebuild)docker compose downStop and remove containerdocker compose logs -fFollow live logsdocker psList running containersdocker ps -aList all containers including stoppeddocker imagesList all imagesdocker system pruneClean up stopped containers and dangling images

Phase 3 Implementation Steps (replaces Steps 16–18 in Section 17)
Step 14 — Confirm Docker Desktop is running
Open Docker Desktop from the Start menu if not already open. Wait for the whale
icon in the taskbar to stop animating.
powershelldocker version
Expected: both Client: and Server: sections print version numbers.
Step 15 — Stop the Phase 2 uvicorn process
powershell# In the terminal where uvicorn is running:
Ctrl+C
Also stop the Phase 2 ngrok session (pointing to port 8000). You will start a new
one pointing to port 10000 in Step 21.
Step 16 — Create Dockerfile, .dockerignore, and docker-compose.yml
Create all three files at the project root exactly as shown in this section.
Verify they exist:
powershellls Dockerfile
ls .dockerignore
ls docker-compose.yml
Step 17 — Build the image and start the container
powershelldocker compose up -d --build
Watch the build output. All steps should complete successfully. The final lines
should read:
=> => naming to docker.io/library/closed-claw_closed-claw
✔ Container closed-claw-dev  Started
Open Docker Desktop → Images. You should see closed-claw listed.
Open Docker Desktop → Containers. You should see closed-claw-dev running (green dot).
If the build fails at the pip install step, check requirements.txt — most
likely pywin32 is missing the sys_platform == 'win32' guard. Fix it and rerun.
Step 18 — Complete first-time Google OAuth
Follow the First-Time Google OAuth Inside Docker steps in this section above.
Done when: ls C:\Users\liang\.google_workspace_mcp\credentials\ shows a token
file and port 8000 has been removed from docker-compose.yml.
Step 19 — Verify health check
powershellcurl http://localhost:10000/health
Expected: {"status":"ok"}
Step 20 — Test agent loop with fake webhook into Docker
powershell$SECRET  = $env:WEBHOOK_SECRET
$CHAT_ID = [int]$env:TELEGRAM_CHAT_ID

$body = @{
    update_id = 100
    message   = @{
        message_id = 1
        chat       = @{ id = $CHAT_ID; type = "private" }
        text       = "What can you help me with?"
        date       = 1700000000
    }
} | ConvertTo-Json -Depth 5

Invoke-WebRequest -Uri "http://localhost:10000/webhook/$SECRET" `
    -Method POST `
    -ContentType "application/json" `
    -Body $body
Expected:

Response body: {"ok":true}
Container logs show the supervisor ran and a response was generated
You may receive an actual Telegram message — this is expected

Step 21 — Start new ngrok tunnel on port 10000
powershellngrok http 10000
Copy the new https:// forwarding URL.
Step 22 — Re-register the Telegram webhook
Update register_webhook.ps1 with the new ngrok URL (port 10000) and run it:
powershell.\register_webhook.ps1
Expected: {"ok": true, "result": true, "description": "Webhook was set"}
Verify:
powershell$TOKEN = $env:TELEGRAM_BOT_TOKEN
Invoke-WebRequest -Uri "https://api.telegram.org/bot$TOKEN/getWebhookInfo" |
    Select-Object -ExpandProperty Content
Confirm the "url" field ends with /webhook/<your-secret> and uses the new
ngrok URL.
Step 23 — Smoke test: real Telegram messages through Docker
Send the same messages from Step 13. Check docker compose logs -f after each.
MessageExpected behaviourWhat can you help me with?Reply in Telegram, no tool call in logsAdd a task called Review report due this FridayTask + calendar event in Google, confirmation in TelegramSend an email to your@gmail.com subject Stage 2 Docker test body Running in DockerEmail delivered, confirmation in Telegram/startAssistant ready. Send me a message.
Phase 3 complete when: All four messages produce the correct behaviour, with
logs confirming the agent loop ran inside the Docker container.

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

## 19. How Stage 3 and Stage 4 Build on This
Stage 2 delivers a working single-user assistant: a message arrives via Telegram,
the agent runs synchronously, a reply is sent. The agent code is stable. The
gateway is thin. The foundation is solid.

The next two stages build upward in two distinct directions. Stage 3 is entirely
about making the assistant smarter and more configurable without touching
infrastructure. Stage 4 is entirely about hardening the infrastructure without
touching agent behaviour. The two stages have no dependencies on each other — the
split is deliberate.

Stage 3 is further split into two sub-stages. Stage 3a establishes how agents are
built, wired, and discovered. Stage 3b enriches those agents with persona and
user knowledge. 3b has no work to do until 3a's foundation is in place.

### Stage 3a — Agent Architecture
Every item in Stage 3a shares one theme: 
- the structure of how agents are built
and discovered is currently rigid. Adding a new agent requires editing Python.
- Changing how an agent behaves requires editing Python. Stage 3a fixes both.

#### Persistent MCP server
Currently workspace-mcp is spawned as a subprocess on the first tool call of
each request and torn down afterward. This causes a 10–20 second cold start on
every fresh container boot. Stage 3a promotes this to a process-level singleton:
workspace-mcp is started once in the FastAPI lifespan handler at app startup
and shared across all requests. 

The `mcps/mcp_pool.py` foundation from Stage 1d
is already in place — Stage 3a wires it into lifespan. Cold starts are
eliminated entirely.

The persistent MCP server must be running before the registry can construct MCP
agents at startup. It is therefore the first thing initialised in lifespan,
before the registry runs.

#### Specialist Skills
Each specialist agent's behavioural instructions — how to format a task, when to
ask a clarifying question, what fields are required for a calendar event — currently
live as strings inside _build_system_prompt(). As the assistant matures those
strings grow, and every edit is a code change.

Skills move those instructions into `skills/<key>/SKILL.md`. Each file is plain
markdown with YAML frontmatter declaring the agent's key, name, type, and a
one-line description. The agent loads only the name and description at startup
(keeping the base prompt lean), and reads the full instruction file on demand
when the skill is relevant to the current request. This is the same pattern
OpenClaw uses — context cost stays low regardless of how many skills exist.

#### Hybrid registry
core/registry.py currently hardcodes which specialist agents exist. Stage 3a
replaces this with a hybrid approach that reflects an important distinction
between agent types:

MCP agents can be fully described in a file — their name, which MCP server
they connect to, their description. The registry can construct them from a
SKILL.md alone. Tasks, calendar, and email are all MCP agents. They live in
skills/ and are discovered by directory scan at startup. Adding a new MCP
agent requires no code change — drop a folder into skills/, restart.

Tool agents call deterministic Python functions directly. Those functions
must exist in code — a file can reference them but cannot contain them. Tool
agents are hardcoded in the registry. Their behavioural instructions still live
in a SKILL.md like any other agent, but their construction requires Python.

The first tool agent introduced in Stage 3a is the reminder agent — a new
specialist that stores and retrieves reminders in a local SQLite table using
Python functions. It sits alongside the three MCP agents in the base set,
demonstrating both agent types working together in the same registry.

The startup sequence is:
1. Start persistent MCP server
2. Build registry
     a. Hardcoded tool agents constructed first (reminders)
     b. `skills/` folder scanned — MCP agents constructed and added
        (tasks, calendar, email — plus any future additions)
3. Construct SupervisorAgent with completed registry

Adding a new MCP specialist in the future: create `skills/<key>/SKILL.md`,
restart. The registry discovers and constructs it automatically. No Python
touched.

### Stage 3b — Behavioural Layer
Stage 3b sits cleanly on top of Stage 3a. The registry, skills, and persistent
MCP server do not change. Stage 3b adds one thing: agents gain knowledge of who
they are and who they are talking to.

Two markdown files are loaded at startup and injected into agent system prompts
alongside the skill instructions:

`memory/agents/<key>.md` — the agent's persona. Tone, communication style,
boundaries, how it introduces itself. Editing this file changes how the agent
behaves on the next restart. No Python touched.

`memory/brain/user.md` — facts about you specifically. Your timezone, preferred
task deadlines, contact name shortcuts, email preferences. The calendar agent
knows you are in MYT. The email agent knows who "David" is. You stop repeating
context the assistant should already hold.

A memory/markdown_store.py loader handles reading these files at startup and
making them available to _build_system_prompt() in each agent.

### Stage 4 — Infrastructure Hardening for Production
Every item in Stage 4 shares one theme: 
- the current infrastructure is sufficient
for a personal single-user assistant but has known limits that matter when the
system runs continuously, survives restarts, or serves more than one user.
PostgreSQL
- SQLite works for development but is file-based and does not survive container
replacement cleanly on hosts with ephemeral filesystems. PostgreSQL replaces it
with a managed persistent database. The schema is simple — agent_turns and
reminders map directly — so migration is straightforward. This is done in
Stage 4 and not earlier because Stage 3 does not change how data is written;
migrating the database mid-stage adds risk for no benefit.
Redis queue

Stage 2's webhook handler awaits the full agent run before returning 200 to
Telegram. For a personal assistant this is acceptable — the single user is patient
and load is low. Stage 4 decouples the two: the webhook handler enqueues the
incoming message and returns 200 immediately; a worker coroutine drains the queue,
runs the agent loop, and sends the reply asynchronously. Telegram's 30-second
timeout becomes irrelevant. This is infrastructure complexity that is not
warranted until the assistant runs continuously in production.

### Proactive reminders
The reminder agent introduced in Stage 3a stores and retrieves reminders on
request. Stage 4 adds the scheduler: APScheduler runs in the lifespan handler,
checks the reminders table on an interval, and sends a Telegram message when
a reminder is due. 

This is introduced alongside Redis rather than in Stage 3a
because a scheduler is background infrastructure — it belongs with the other
always-on process concerns.

### Multi-user OAuth
The most complex item in Stage 4. Currently the gateway allowlists a single
TELEGRAM_CHAT_ID and reads a single Google credential from disk. Multi-user
OAuth replaces this with dynamic user registration: when an unknown chat_id
messages the bot, the gateway generates a Google auth URL and sends it to that
user. 

A new /oauth/callback endpoint receives the authorisation code, exchanges
it for a token, and persists the credential against that chat_id. Subsequent
requests look up the credential for the requesting user.

This changes the security model of the gateway, the shape of AgentDeps, and
requires the PostgreSQL store from earlier in Stage 4 to persist credentials.
It is the last item in Stage 4 for this reason — it depends on everything else
in that stage being in place first.

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