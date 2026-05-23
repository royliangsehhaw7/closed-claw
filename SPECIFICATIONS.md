# Personal Telegram Assistant
## Specification — Stage 1b: MCP Verification (v3 — using `workspace-mcp`)

> **Replaces:** SPECIFICATION_1B_v2.md (gws — abandoned, `gws mcp` subcommand removed at v0.8.0)
>
> **Assumes:** Stage 1a complete and merged to `main`
>
> **Branch:** `stage/1b` branched from `main` after Stage 1a merge
>
> **Done when:** A PydanticAI agent using `workspace-mcp` can receive a plain English
> instruction, choose the correct MCP tool, and produce a real result in Google.
> A task created via the tasks test appears in Google Tasks. A calendar event
> appears in Google Calendar. An email is delivered via Gmail. All interactions
> logged to file. No Supervisor, no Telegram, no Redis — single-agent MCP
> verification only.

---

## 1. What Changed and Why

`gws` was abandoned. The `gws mcp` subcommand shipped in v0.5.0 and was removed
two days later in v0.8.0. v0.22.5 (current) has no MCP mode. All community
wrappers (`gws-mcp-server`) are incomplete — Tasks not supported.

`workspace-mcp` (`pip install workspace-mcp` / `uvx workspace-mcp`) replaces it.
It is a Python MCP server maintained by taylorwilsdon, built on FastMCP, covering
Gmail, Calendar, Drive, Docs, Sheets, Slides, Forms, Tasks, Chat, and more.

For this stage (single personal account), we use **single-user mode with stdio
transport**. This is the simplest possible setup:

- Run `workspace-mcp` as a subprocess via `MCPServerStdio`
- Auth is done once via a browser OAuth flow triggered on first tool call
- Credentials are saved to disk as a JSON file per email
- All subsequent calls are silent — no browser, no prompt

No OAuth 2.1. No bearer tokens. No HTTP server. Just stdio, exactly like the
original spec intended.

---

## 2. What `workspace-mcp` Is

Python MCP server published on PyPI as `workspace-mcp`.
GitHub: https://github.com/taylorwilsdon/google_workspace_mcp

Covers: Gmail, Calendar, Drive, Docs, Sheets, Slides, Forms, Tasks, Chat,
Contacts, Apps Script, Custom Search.

Transport modes: stdio (default), streamable-http, SSE.

For single personal user: stdio + single-user mode. Auth happens once, credentials
cached on disk. No re-auth until token expires or is revoked.

---

## 3. Pre-Code Setup — Complete Step-by-Step

**Do every step in order. Verify each before moving on.
Do not write any code until all steps are complete.**

---

### Step 1 — Install `uv`

`workspace-mcp` is best run via `uvx` (from the `uv` package manager). If you
already have `uv`, skip this.

```powershell
pip install uv
```

Verify:

```powershell
uv --version
uvx --version
```

Both should print version strings. If `uvx` is not found after install, close
and reopen PowerShell.

---

### Step 2 — Verify `workspace-mcp` installs and runs

```powershell
uvx workspace-mcp --help
```

Expected: a help message listing flags like `--transport`, `--tools`,
`--single-user`, `--tool-tier`.

If this fails, try installing directly first:

```powershell
pip install workspace-mcp
workspace-mcp --help
```

Note the full path to the binary for use in Step 8 if needed:

```powershell
where.exe workspace-mcp
# or
python -m site --user-base
```

---

### Step 3 — Verify Google Cloud project and APIs

You already have a Google Cloud project from Stage 1a. Confirm the correct APIs
are enabled at https://console.cloud.google.com/apis/dashboard

Enable each of these if not already on:

- Google Tasks API
- Google Calendar API
- Gmail API
- Google Drive API

If any are missing: click **Enable APIs and Services**, search by name, enable,
wait 30 seconds before proceeding.

---

### Step 4 — Create a Desktop OAuth client

Go to https://console.cloud.google.com/apis/credentials

You need an OAuth 2.0 Client ID of type **Desktop app**.

If you only have a Web Application type from Stage 1a, create a new one:

1. Click **Create Credentials → OAuth client ID**
2. Select **Desktop app**
3. Name it `closed-claw-desktop`
4. Click **Create**
5. Note the **Client ID** and **Client Secret** — you need them in Step 5

If you already have a Desktop app credential, use that.

---

### Step 5 — Add credentials to `.env`

Add these to your existing `.env` file:

```
GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
USER_GOOGLE_EMAIL=your-email@gmail.com
```

`USER_GOOGLE_EMAIL` sets the default account for single-user mode. Without it,
`workspace-mcp` will prompt for an email on first tool call.

---

### Step 6 — Set env vars in your current PowerShell session

The OAuth flow in Step 7 requires these to be set in the shell that runs
`workspace-mcp`. Set them now:

```powershell
$env:GOOGLE_OAUTH_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
$env:GOOGLE_OAUTH_CLIENT_SECRET = "your-client-secret"
$env:USER_GOOGLE_EMAIL = "your-email@gmail.com"
$env:OAUTHLIB_INSECURE_TRANSPORT = "1"
```

Verify they are set:

```powershell
echo $env:GOOGLE_OAUTH_CLIENT_ID
echo $env:GOOGLE_OAUTH_CLIENT_SECRET
echo $env:USER_GOOGLE_EMAIL
```

All three should print non-empty values.

---

### Step 7 — Complete the one-time OAuth flow via MCP Inspector

**This step is done exactly once per Google account. After it completes,
credentials are saved to disk and auth never appears again.**

Run MCP Inspector — it starts the server for you:

```powershell
npx @modelcontextprotocol/inspector
```

A browser tab opens automatically at `http://localhost:6274`. Fill in the form:

- **Transport Type:** STDIO
- **Command:** `uvx`
- **Arguments:** `workspace-mcp --single-user --tools tasks`
- Expand **Environment Variables** and add all four:
  - `GOOGLE_OAUTH_CLIENT_ID` = your client id
  - `GOOGLE_OAUTH_CLIENT_SECRET` = your client secret
  - `USER_GOOGLE_EMAIL` = your email
  - `OAUTHLIB_INSECURE_TRANSPORT` = `1`

Click **Connect**. Once connected, click the **Tools** tab in the left sidebar.
Find `list_task_lists` and click **Run Tool**.

The tool result panel will show a message like:

```
ACTION REQUIRED: Google Authentication Needed
Please visit this URL to authenticate: https://accounts.google.com/o/oauth2/...
```

Copy the full URL from that result panel and open it in your browser.

What happens next:
1. Select your Google account
2. If "Google hasn't verified this app" appears: click **Advanced** → **Go to app (unsafe)**
3. Review scopes and click **Allow**
4. Browser shows a success page

Go back to MCP Inspector and click **Run Tool** again on `list_task_lists`.
This time it returns your actual task lists as JSON — auth is complete.

Credentials are now saved to disk at:
```
C:\Users\<you>\AppData\Roaming\workspace-mcp\credentials\your-email@gmail.com.json
```

Close MCP Inspector. Auth is done. It will not be asked again for this account.

---

### Step 8 — Verify auth works for all services

Repeat Step 7 for Calendar and Gmail — same Inspector flow, different `--tools` flag.
Each service needs its own tool call to confirm auth covers the right scopes.

**Calendar:**

In Inspector Arguments field: `workspace-mcp --single-user --tools calendar`

Click Connect → Tools → `list_calendars` → Run Tool.
Expected: JSON list of your calendars. If auth prompt appears again, complete
it the same way as Step 7.

**Gmail:**

In Inspector Arguments field: `workspace-mcp --single-user --tools gmail`

Click Connect → Tools → `search_gmail_messages` → set query to `in:inbox` → Run Tool.
Expected: JSON list of messages.

Do not proceed until all three services return real data without an auth prompt.

---

### Step 9 — Verify `workspace-mcp` is accessible from Python subprocess

Create a throwaway script `verify_workspace_mcp.py` in the project root:

```python
import subprocess, shutil, os

# Try uvx first, fall back to direct binary
cmd = shutil.which("uvx") or shutil.which("workspace-mcp")
print(f"Command found: {cmd}")

args = ["uvx", "workspace-mcp", "--help"] if "uvx" in (cmd or "") else ["workspace-mcp", "--help"]

result = subprocess.run(
    args,
    capture_output=True,
    text=True,
    env={**os.environ}
)
print(f"returncode: {result.returncode}")
print(f"stdout: {result.stdout[:300]}")
print(f"stderr: {result.stderr[:300]}")
```

Run it:

```powershell
python verify_workspace_mcp.py
```

Expected: `returncode: 0` and the help text in stdout. If it fails, Python
cannot find `uvx` or `workspace-mcp` on PATH. Fix: add the directory shown by
`where.exe uvx` to your system PATH permanently (System Properties →
Environment Variables → Path).

Delete `verify_workspace_mcp.py` after it passes.

---

### Step 10 — Confirm credentials dir and `.env` are complete

Your `.env` should now contain:

```
# From Stage 1a (unchanged)
ANTHROPIC_API_KEY=...

# workspace-mcp Google OAuth
GOOGLE_OAUTH_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=your-client-secret
USER_GOOGLE_EMAIL=your-email@gmail.com

# Test email for Gmail test
TEST_EMAIL_ADDRESS=you@gmail.com
```

The credentials file written during Step 7 must exist:
```powershell
dir "$env:APPDATA\workspace-mcp\credentials\"
```
You should see a `.json` file named after your email.

---

## 4. Architecture

```
Test script (Python)
   │  agent.run("Create a task called...")
   ▼
PydanticAI Agent
   │  discovers tools, selects correct one, constructs arguments
   ▼
MCPServerStdio
   │  spawns: uvx workspace-mcp --single-user --tools tasks
   │  communicates over stdin/stdout pipes
   ▼
workspace-mcp server
   │  reads cached credentials from disk silently
   ▼
Google Tasks API
   │  creates task, returns result
   ▼
workspace-mcp → MCPServerStdio → Agent → response string
```

Auth never appears in this flow after the one-time browser consent in Step 7.

---

## 5. File Changes from Stage 1a

### New files this stage:
```
app/mcp/
    __init__.py
    google.py           ← MCP server wrapper
tests/
    __init__.py
    scratch_list_tools.py   ← optional, delete after use
    test_mcp_tasks.py
    test_mcp_calendar.py
    test_mcp_gmail.py
```

### Updated files:
```
.env                    ← add GOOGLE_OAUTH_CLIENT_ID/SECRET/USER_GOOGLE_EMAIL
requirements.txt        ← add workspace-mcp
```

---

## 6. `requirements.txt` addition

```
workspace-mcp
```

Or if running via uvx (no local install needed), add a comment only:

```
# System MCP server (run via uvx, not pip):
# uvx workspace-mcp
# Auth setup: see SPECIFICATION_1B_v3.md Step 7
```

---

## 7. `app/mcp/__init__.py`

```python
from app.mcp.google import google_workspace_server

__all__ = ["google_workspace_server"]
```

---

## 8. `app/mcp/google.py`

```python
"""Google Workspace MCP server wrapper using workspace-mcp.

workspace-mcp is a Python MCP server (pip install workspace-mcp) that exposes
Gmail, Calendar, Drive, Docs, Sheets, Slides, Forms, Tasks, Chat, and more
as MCP tools over stdio.

Auth: one-time browser OAuth flow on first tool call. Credentials cached to
disk per email. All subsequent calls are silent.

Usage:
    google_workspace_server(["tasks"])
    google_workspace_server(["tasks", "calendar"])
    google_workspace_server(["gmail"])

Valid service names: gmail, drive, calendar, docs, sheets, slides, forms,
                     tasks, chat, search
"""

import os
import shutil
from pydantic_ai.mcp import MCPServerStdio


def google_workspace_server(services: list[str]) -> MCPServerStdio:
    """Return a configured MCPServerStdio for the given Google Workspace services.

    Spawns workspace-mcp via uvx (preferred) or direct binary. Runs in
    single-user mode — credentials are read from disk after one-time OAuth.

    Args:
        services: list of service names, e.g. ["tasks", "calendar"]

    Returns:
        MCPServerStdio configured to spawn workspace-mcp for the given services.

    Raises:
        RuntimeError: if neither uvx nor workspace-mcp binary is found on PATH.
    """
    uvx_path = shutil.which("uvx")
    wsmcp_path = shutil.which("workspace-mcp")

    if uvx_path:
        command = uvx_path
        args = [
            "workspace-mcp",
            "--single-user",
            "--tools", " ".join(services),
        ]
    elif wsmcp_path:
        command = wsmcp_path
        args = [
            "--single-user",
            "--tools", " ".join(services),
        ]
    else:
        raise RuntimeError(
            "Neither uvx nor workspace-mcp found on PATH.\n"
            "Install with: pip install uv && pip install workspace-mcp\n"
            "Then complete OAuth setup: see SPECIFICATION_1B_v3.md Step 7."
        )

    return MCPServerStdio(
        command,
        args=args,
        env={
            **os.environ,
            "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "USER_GOOGLE_EMAIL": os.getenv("USER_GOOGLE_EMAIL", ""),
            "OAUTHLIB_INSECURE_TRANSPORT": "1",
        },
    )
```

---

## 9. `tests/scratch_list_tools.py` (optional — delete after use)

```python
"""Print all MCP tools available for each service.

Run with: python -m tests.scratch_list_tools
Delete after use.
"""

import asyncio
from app.mcp.google import google_workspace_server


async def list_tools(services: list[str]) -> None:
    server = google_workspace_server(services)
    async with server:
        tools = await server.list_tools()
        print(f"\n--- {services} ({len(tools)} tools) ---")
        for tool in tools:
            print(f"  {tool.name}: {tool.description[:80] if tool.description else ''}")


async def main() -> None:
    await list_tools(["tasks"])
    await list_tools(["calendar"])
    await list_tools(["gmail"])


if __name__ == "__main__":
    asyncio.run(main())
```

---

## 10. `tests/test_mcp_tasks.py`

```python
"""Stage 1b — Google Tasks MCP verification.

Run with: python -m tests.test_mcp_tasks
"""

import asyncio
import logging
from pydantic_ai import Agent
from core.llm_factory import LLMFactory
from app.mcp.google import google_workspace_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/assistant.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("app")
_factory = LLMFactory()


async def run() -> None:
    agent = Agent(
        model=_factory.get_model(),
        mcp_servers=[google_workspace_server(["tasks"])],
        system_prompt=(
            "You are a task management assistant. "
            "Carry out the user's instruction exactly using the available tools. "
            "Confirm what you did in one sentence."
        ),
    )

    async with agent.run_mcp_servers():

        # Step 1 — Create
        logger.info("TEST | tasks | step=1 | create")
        result = await agent.run(
            "Create a task called '[1b test] MCP verification task'. "
            "Set the due date to tomorrow. "
            "Put it in the 'Development' list if it exists, otherwise My Tasks. "
            "Add a note: Created by test_mcp_tasks.py — safe to delete."
        )
        logger.info("TEST | tasks | step=1 | response=%r", result.output)
        print(f"\nStep 1 — Create\n  Agent: {result.output}")
        print("  → Open Google Tasks and confirm the task appears.")
        input("  Press Enter when confirmed...\n")

        # Step 2 — Update
        logger.info("TEST | tasks | step=2 | update")
        result = await agent.run(
            "Update the task called '[1b test] MCP verification task'. "
            "Change the title to '[1b test] MCP verification task — UPDATED'."
        )
        logger.info("TEST | tasks | step=2 | response=%r", result.output)
        print(f"Step 2 — Update\n  Agent: {result.output}")
        print("  → Confirm the title updated in Google Tasks.")
        input("  Press Enter when confirmed...\n")

        # Step 3 — Delete
        logger.info("TEST | tasks | step=3 | delete")
        result = await agent.run(
            "Delete the task called '[1b test] MCP verification task — UPDATED'."
        )
        logger.info("TEST | tasks | step=3 | response=%r", result.output)
        print(f"Step 3 — Delete\n  Agent: {result.output}")
        print("  → Confirm the task is gone from Google Tasks.")
        input("  Press Enter when confirmed...\n")

    print("Tasks test complete.")


if __name__ == "__main__":
    asyncio.run(run())
```

---

## 11. `tests/test_mcp_calendar.py`

```python
"""Stage 1b — Google Calendar MCP verification.

Run with: python -m tests.test_mcp_calendar
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pydantic_ai import Agent
from core.llm_factory import LLMFactory
from app.mcp.google import google_workspace_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/assistant.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("app")
_factory = LLMFactory()


async def run() -> None:
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    agent = Agent(
        model=_factory.get_model(),
        mcp_servers=[google_workspace_server(["calendar"])],
        system_prompt=(
            "You are a calendar assistant. "
            "Carry out the user's instruction exactly using the available tools. "
            "Confirm what you did in one sentence."
        ),
    )

    async with agent.run_mcp_servers():

        # Step 1 — Create
        logger.info("TEST | calendar | step=1 | create")
        result = await agent.run(
            f"Create a calendar event called '[1b test] MCP verification event' "
            f"on {tomorrow} from 10:00 AM to 11:00 AM. "
            f"Add description: Created by test_mcp_calendar.py — safe to delete."
        )
        logger.info("TEST | calendar | step=1 | response=%r", result.output)
        print(f"\nStep 1 — Create\n  Agent: {result.output}")
        print("  → Open Google Calendar and confirm the event appears.")
        input("  Press Enter when confirmed...\n")

        # Step 2 — Update
        logger.info("TEST | calendar | step=2 | update")
        result = await agent.run(
            "Update the event '[1b test] MCP verification event'. "
            "Change the description to: UPDATED by test_mcp_calendar.py."
        )
        logger.info("TEST | calendar | step=2 | response=%r", result.output)
        print(f"Step 2 — Update\n  Agent: {result.output}")
        print("  → Confirm the description updated in Google Calendar.")
        input("  Press Enter when confirmed...\n")

    print("Calendar test complete. Delete the test event manually.")


if __name__ == "__main__":
    asyncio.run(run())
```

---

## 12. `tests/test_mcp_gmail.py`

```python
"""Stage 1b — Gmail MCP verification.

Run with: python -m tests.test_mcp_gmail

Requires TEST_EMAIL_ADDRESS in .env.
"""

import asyncio
import logging
import os
from pydantic_ai import Agent
from core.llm_factory import LLMFactory
from app.mcp.google import google_workspace_server

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
    handlers=[
        logging.FileHandler("logs/assistant.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("app")
_factory = LLMFactory()


async def run() -> None:
    test_email = os.getenv("TEST_EMAIL_ADDRESS")
    if not test_email:
        raise ValueError("TEST_EMAIL_ADDRESS not set in .env")

    agent = Agent(
        model=_factory.get_model(),
        mcp_servers=[google_workspace_server(["gmail"])],
        system_prompt=(
            "You are an email assistant. "
            "Carry out the user's instruction exactly using the available tools. "
            "Confirm what you did in one sentence."
        ),
    )

    async with agent.run_mcp_servers():

        logger.info("TEST | gmail | step=1 | send")
        result = await agent.run(
            f"Send an email to {test_email} with subject "
            "'[1b test] MCP Gmail verification' and body "
            "'This email was sent by test_mcp_gmail.py — safe to delete.'"
        )
        logger.info("TEST | gmail | step=1 | response=%r", result.output)
        print(f"\nStep 1 — Send\n  Agent: {result.output}")
        print(f"  → Check inbox at {test_email}.")
        input("  Press Enter when confirmed...\n")

    print("Gmail test complete.")


if __name__ == "__main__":
    asyncio.run(run())
```

---

## 13. Implementation Sequence

**Step 1 — Complete all of Section 3 (Pre-Code Setup)**
Every verification must pass before writing code. Do not skip.

**Step 2 — Create folder structure**
```powershell
mkdir -Force app\mcp
New-Item -Force app\mcp\__init__.py
New-Item -Force tests\__init__.py
mkdir -Force logs
```

**Step 3 — Implement `app/mcp/google.py` and `app/mcp/__init__.py`**
Exactly as specified in Sections 8 and 7.

**Step 4 — Optional: run `scratch_list_tools.py`**
```powershell
python -m tests.scratch_list_tools
```
Confirms tool list is what you expect. Delete after use.

**Step 5 — Run `test_mcp_tasks.py`**
```powershell
python -m tests.test_mcp_tasks
```

**Step 6 — Run `test_mcp_calendar.py`**
```powershell
python -m tests.test_mcp_calendar
```

**Step 7 — Run `test_mcp_gmail.py`**
Set `TEST_EMAIL_ADDRESS` in `.env` first.
```powershell
python -m tests.test_mcp_gmail
```

---

## 14. Troubleshooting

**`uvx: command not found`**
Run `pip install uv` then close and reopen PowerShell.

**`workspace-mcp --help` fails**
Run `pip install workspace-mcp` directly. Then `where.exe workspace-mcp` and
confirm the path is on your system PATH.

**OAuth browser flow triggers every run**
Credentials were not saved. Check that the credentials directory exists and
contains a `.json` file for your email. If not, redo Step 7 and let the full
flow complete before pressing Ctrl+C.

**`MCPServerStdio` connection closed error**
workspace-mcp printed something to stdout before the JSON-RPC handshake. Run
it manually and watch what it prints on startup:
```powershell
uvx workspace-mcp --single-user --tools tasks 2>err.log
```
Anything on stdout before the first `{` is the problem.

**`403 accessNotConfigured`**
The Google API is not enabled in your GCP project. Enable it at
https://console.cloud.google.com/apis/dashboard, wait 30 seconds, retry.

**Agent responds but nothing appears in Google**
The LLM called a tool but something went wrong. Check `logs/assistant.log` for
the full exchange. Run `scratch_list_tools.py` to confirm tools are visible.
Rephrase the instruction more explicitly.

**`USER_GOOGLE_EMAIL` not being picked up**
Confirm it is in `.env` AND loaded before the subprocess spawns. Your
`app/mcp/google.py` passes it explicitly via the `env` dict — verify that dict
is being constructed correctly.

---

## 15. Production Notes (reference — not built this stage)

Credentials are saved at:
```
Windows: %APPDATA%\workspace-mcp\credentials\email.json
Linux:   ~/.local/share/workspace-mcp/credentials/email.json
```

For Linux VPS deployment:
1. `pip install workspace-mcp` on the VPS
2. Set env vars and run once interactively to complete OAuth (requires browser)
3. Mount or copy the credentials directory to Docker:

```yaml
volumes:
  - ~/.local/share/workspace-mcp:/root/.local/share/workspace-mcp
```

One auth per environment. After that, fully silent.

---

## 16. How Stage 1c Wires These to Agents

Nothing changes in `app/mcp/`. Same function, different service lists:

```python
# Stage 1c — agents/concierge.py
from app.mcp.google import google_workspace_server

agent = Agent(
    model=_factory.get_model(),
    mcp_servers=[google_workspace_server(["tasks", "calendar"])],
    system_prompt="...",
)
```

```python
# Stage 1c — agents/comms.py
from app.mcp.google import google_workspace_server

agent = Agent(
    model=_factory.get_model(),
    mcp_servers=[google_workspace_server(["gmail"])],
    system_prompt="...",
)
```

---

## 17. Note on Multiple Users

The one-time OAuth flow in Step 7 is per Google account — not per app install.
Every Google integration in the world works this way (Notion, Zapier, any Gmail
connector). Google requires a real browser consent from the actual user before
any app can touch their data. There is no way around this.

For the Telegram bot when it goes multi-user:

1. A new user starts the bot
2. Bot detects no credentials on disk for their account
3. Bot sends them a Telegram message with the Google auth URL
4. User taps the link, completes consent in browser once
5. Credentials saved to disk, bot works silently forever after for that user

Each user's credentials are stored as a separate JSON file named after their
email. No user can see another user's credentials. The flow is the same as
Step 7 — just triggered from Telegram instead of MCP Inspector.

This is a Stage 2+ concern. Nothing in the current codebase needs to change
to support it — `workspace-mcp` already handles per-user credential files.

---

## 18. Done When

- Section 3 (Pre-Code Setup) fully complete — all terminal verification
  commands return real data, credentials JSON file exists on disk
- `python -m tests.test_mcp_tasks` completes all three steps; task appears
  in Google Tasks after create, title updates, task is gone after delete
- `python -m tests.test_mcp_calendar` completes both steps; event appears in
  Google Calendar at the correct time, description updates
- `python -m tests.test_mcp_gmail` completes; email arrives in inbox with
  correct subject and body
- In all three tests, agent response describes what it actually did —
  not just an echo of the instruction
- All test runs produce log lines in `logs/assistant.log`
- `from app.mcp import google_workspace_server` imports cleanly
- No Supervisor, no Telegram, no Redis — single-agent MCP verification only