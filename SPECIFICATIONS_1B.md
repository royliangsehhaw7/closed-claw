# Personal Telegram Assistant
## Specification — Stage 1b: MCP Verification (v2 — using `gws`)

> **Replaces:** SPECIFICATION_1B.md (workspace-mcp — abandoned)
>
> **Assumes:** Stage 1a complete and merged to `main`
>
> **Branch:** `stage/1b` branched from `main` after Stage 1a merge
>
> **Done when:** A PydanticAI agent using `gws mcp` can receive a plain English
> instruction, choose the correct MCP tool, and produce a real result in Google.
> A task created via the tasks test appears in Google Tasks. A calendar event
> appears in Google Calendar. An email is delivered via Gmail. All interactions
> logged to file. No Supervisor, no Telegram, no Redis — single-agent MCP
> verification only.

---

## 1. What Changed and Why

`workspace-mcp` was abandoned after it repeatedly failed to read cached tokens
and returned OAuth URLs to the caller instead of handling auth internally. The
root cause is that `workspace-mcp` defaults to multi-user mode, expects its own
internal token format, and its auth flow depends on a browser callback that
never reliably completed in a subprocess context on Windows.

`gws` (`@googleworkspace/cli`) replaces it. The key difference:

- Auth is a **completely separate CLI command** (`gws auth login`) that has
  nothing to do with the MCP server
- The MCP server (`gws mcp`) never touches auth — it reads encrypted credentials
  silently from the OS keyring
- No token file format to match. No scope lists to maintain. No auth callback
  server to keep alive

---

## 2. What `gws` Is

`gws` is an open-source CLI written in Rust, published under the `googleworkspace`
GitHub organisation. It is **not** an officially supported Google product, but it
is Google-built, actively maintained, and the correct tool for this use case.

It reads Google's Discovery Service at runtime and builds its entire command
surface dynamically — including Tasks, Calendar, Gmail, Drive, and more.

It ships with a built-in MCP server that exposes all Workspace APIs over stdio.
PydanticAI connects to it via `MCPServerStdio` exactly as before — only the
binary changes.

GitHub: https://github.com/googleworkspace/cli
npm: https://www.npmjs.com/package/@googleworkspace/cli

---

## 3. Pre-Code Setup — Complete Step-by-Step

**Do every step in order. Verify each step before moving to the next.
Do not write any code until Section 3 is fully complete.**

---

### Step 1 — Verify Node.js is installed

`gws` is distributed via npm. Node.js is required.

```powershell
node --version
npm --version
```

Expected output: `v18.x.x` or higher for Node, any version for npm.

If not installed: https://nodejs.org — download and install the LTS version,
then re-open PowerShell and verify the commands above.

---

### Step 2 — Install `gws`

```powershell
npm install -g @googleworkspace/cli
```

Verify the install succeeded:

```powershell
gws --version
```

Expected output: a version string like `0.22.5`. If `gws` is not found, close
and reopen PowerShell (PATH needs to refresh after npm global install).

If still not found after reopening:
```powershell
# Find where npm puts global binaries
npm config get prefix
# Add that path + \bin to your system PATH if missing
```

---

### Step 3 — Verify Google Cloud project and APIs

You already have a Google Cloud project from Stage 1a. You need to confirm the
correct APIs are enabled. Go to:

https://console.cloud.google.com/apis/dashboard

Confirm these APIs are enabled (search for each by name):
- Google Tasks API
- Google Calendar API
- Gmail API

If any are missing, click **Enable APIs and Services**, search for the API,
and enable it. Wait 30 seconds after enabling before proceeding.

**One-time gotcha:** `gws` will also print the exact enable URL if you hit a
403 on first use. That is normal — just click the link, enable, and retry.

---

### Step 4 — Verify your OAuth client credentials

You already have an OAuth 2.0 Client ID from Stage 1a. Confirm:

1. Go to https://console.cloud.google.com/apis/credentials
2. Find your OAuth 2.0 Client ID
3. Confirm the type is **Desktop app**
4. Note the Client ID and Client Secret — you will need them in Step 5

If you only have a Web Application type, create a new Desktop app credential:
- Click **Create Credentials → OAuth client ID**
- Select **Desktop app**
- Name it anything (e.g. `closed-claw-desktop`)
- Copy the Client ID and Client Secret

---

### Step 5 — Set credentials as environment variables

`gws auth setup` is broken on Windows (known issue — Rust cannot resolve
`.cmd` wrapper executables). Use environment variables instead — they work
reliably on Windows.

**Set them permanently in your `.env` file:**

```
GOOGLE_WORKSPACE_CLI_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_WORKSPACE_CLI_CLIENT_SECRET=your-client-secret
```

**Also set them in your current PowerShell session for the auth steps below:**

```powershell
$env:GOOGLE_WORKSPACE_CLI_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
$env:GOOGLE_WORKSPACE_CLI_CLIENT_SECRET = "your-client-secret"
```

Verify they are set:

```powershell
echo $env:GOOGLE_WORKSPACE_CLI_CLIENT_ID
echo $env:GOOGLE_WORKSPACE_CLI_CLIENT_SECRET
```

Both should print non-empty values. Do not proceed until they do.

---

### Step 6 — Run `gws auth login`

```powershell
gws auth login
```

What happens:
1. An interactive scope selector appears in the terminal — all scopes are
   pre-selected. Press Enter to accept all.
2. A browser opens to Google's OAuth consent screen.
3. Select your Google account.
4. If the "Google hasn't verified this app" warning appears:
   click **Advanced** → **Go to [app name] (unsafe)**
5. Review and click **Allow**.
6. The terminal prints a JSON confirmation:

```json
{
  "credentials_file": "C:\\Users\\liang\\AppData\\Roaming\\gws\\credentials.enc",
  "encryption": "AES-256-GCM (key secured by OS Keyring or local .encryption_key)",
  "message": "Authentication successful. Encrypted credentials saved.",
  "status": "success"
}
```

**This is a one-time step.** Credentials are encrypted with AES-256-GCM and
stored in the OS keyring. All future `gws` calls — including from your Python
subprocess — read these credentials silently. No browser, no prompt, ever again.

---

### Step 7 — Verify auth works from the terminal

Test each service with a simple read command. These confirm the credentials
work AND the APIs are enabled.

**Tasks:**
```powershell
gws tasks tasklists list
```
Expected: JSON list of your task lists. If you get a 403 with
`accessNotConfigured`, click the URL it prints, enable the API, wait 30 seconds,
retry.

**Calendar:**
```powershell
gws calendar calendarlist list
```
Expected: JSON list of your calendars.

**Gmail:**
```powershell
gws gmail users labels list --params "{\"userId\": \"me\"}"
```
Expected: JSON list of your Gmail labels.

**Do not proceed to Step 8 until all three commands return valid JSON.**
If any fail, fix them now. A failure here means the same failure will happen
in your Python code, but it will be harder to diagnose there.

---

### Step 8 — Verify `gws mcp` starts correctly

```powershell
gws mcp -s tasks,calendar,gmail
```

Expected output (it will hang — that is correct, it is waiting for an MCP client):
```
Starting MCP server...
Loaded services: tasks, calendar, gmail
Listening on stdio
```

Press `Ctrl+C` to stop it.

If it errors instead of hanging, fix the error before proceeding.

---

### Step 9 — Verify `gws` is accessible from Python subprocess

Create a quick throwaway script `verify_gws.py` in the project root:

```python
import subprocess, shutil

path = shutil.which("gws")
print(f"gws path: {path}")

result = subprocess.run(
    ["gws", "tasks", "tasklists", "list"],
    capture_output=True, text=True
)
print(f"returncode: {result.returncode}")
print(f"stdout: {result.stdout[:200]}")
print(f"stderr: {result.stderr[:200]}")
```

Run it:
```powershell
python verify_gws.py
```

Expected: `returncode: 0` and JSON in stdout.

If `gws path: None` — Python cannot find `gws` on PATH. This will also break
`MCPServerStdio`. Fix: find the full path with `where gws` in PowerShell and
use the absolute path in your MCP wrapper (see Section 7).

Delete `verify_gws.py` after it passes.

---

### Step 10 — Add `gws` credentials to `.env`

Your `.env` should now contain (in addition to existing keys):

```
GOOGLE_WORKSPACE_CLI_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_WORKSPACE_CLI_CLIENT_SECRET=your-client-secret
```

These are passed through to the `gws` subprocess by your MCP wrapper so it
can find credentials when spawned by Python (see Section 7).

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
   │  spawns: gws mcp -s tasks (subprocess)
   │  communicates over stdin/stdout pipes
   ▼
gws MCP server
   │  reads encrypted credentials from OS keyring silently
   ▼
Google Tasks API
   │  creates task, returns result
   ▼
gws → MCPServerStdio → Agent → response string
```

Auth never appears in this flow after the one-time `gws auth login` in Step 6.

---

## 5. File Changes from Stage 1a

### New files this stage:
```
app/mcp/
    __init__.py
    google.py           ← MCP server wrapper (replaces workspace-mcp version)
tests/
    __init__.py
    scratch_list_tools.py   ← optional, delete after use
    test_mcp_tasks.py
    test_mcp_calendar.py
    test_mcp_gmail.py
```

### Updated files:
```
.env                    ← add GOOGLE_WORKSPACE_CLI_CLIENT_ID/SECRET
requirements.txt        ← no new Python deps needed (gws is a system binary)
```

---

## 6. `app/mcp/__init__.py`

```python
from app.mcp.google import google_workspace_server

__all__ = ["google_workspace_server"]
```

---

## 7. `app/mcp/google.py`

```python
"""Google Workspace MCP server wrapper using gws CLI.

gws (googleworkspace/cli) is a Rust binary that exposes all Google Workspace
APIs as an MCP server over stdio. Auth is handled entirely by the gws binary
using credentials stored in the OS keyring after a one-time `gws auth login`.

Usage:
    google_workspace_server(["tasks"])             # Tasks only
    google_workspace_server(["tasks", "calendar"]) # Concierge agent
    google_workspace_server(["gmail"])             # Comms agent

Valid service names: tasks, calendar, gmail, drive, docs, sheets, slides,
                     forms, chat, contacts
"""

import os
import shutil
from pydantic_ai.mcp import MCPServerStdio


def google_workspace_server(services: list[str]) -> MCPServerStdio:
    """Return a configured MCPServerStdio for the given Google Workspace services.

    Args:
        services: list of service names to enable, e.g. ["tasks", "calendar"]

    Returns:
        MCPServerStdio configured to spawn gws mcp for the given services.

    Raises:
        RuntimeError: if gws binary is not found on PATH.
    """
    gws_path = shutil.which("gws")
    if gws_path is None:
        raise RuntimeError(
            "gws binary not found on PATH. "
            "Install it with: npm install -g @googleworkspace/cli\n"
            "If already installed, find the full path with `where gws` "
            "(Windows) or `which gws` (Unix) and set GWS_PATH in .env."
        )

    return MCPServerStdio(
        gws_path,
        args=["mcp", "-s", ",".join(services)],
        env={
            **os.environ,  # inherit full environment including PATH
            "GOOGLE_WORKSPACE_CLI_CLIENT_ID": os.getenv(
                "GOOGLE_WORKSPACE_CLI_CLIENT_ID", ""
            ),
            "GOOGLE_WORKSPACE_CLI_CLIENT_SECRET": os.getenv(
                "GOOGLE_WORKSPACE_CLI_CLIENT_SECRET", ""
            ),
        },
    )
```

**Why `shutil.which`:** Python subprocesses do not always inherit the same
PATH as your shell, especially when launched from an IDE or Docker. Using the
full resolved path avoids silent failures.

**Why `**os.environ`:** `MCPServerStdio`'s `env` parameter replaces the
subprocess environment entirely — it does not merge. Without `**os.environ`,
the subprocess gets only the two credential vars and nothing else, which breaks
`gws` because it cannot find its own runtime dependencies.

---

## 8. `tests/scratch_list_tools.py` (optional, delete after use)

Run this before the agent tests to confirm what tools the LLM can see.
Not required — delete after use.

```python
"""Print all MCP tools available for each service.

Run with: python -m tests.scratch_list_tools
Delete this file after use — it is not part of the test suite.
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

## 9. `tests/test_mcp_tasks.py`

```python
"""Stage 1b — Google Tasks MCP verification.

Run with: python -m tests.test_mcp_tasks

Tests:
    Step 1 — Create a task in the default task list
    Step 2 — List tasks to confirm it exists
    Step 3 — Delete the task

Each step pauses for manual confirmation in Google Tasks.
"""

import asyncio
import logging
from pydantic_ai import Agent
from app.core.llm_factory import LLMFactory
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

## 10. `tests/test_mcp_calendar.py`

```python
"""Stage 1b — Google Calendar MCP verification.

Run with: python -m tests.test_mcp_calendar

Tests:
    Step 1 — Create a calendar event tomorrow at 9am
    Step 2 — Update the event description

Delete the event manually from Google Calendar after the test.
"""

import asyncio
import logging
from pydantic_ai import Agent
from app.core.llm_factory import LLMFactory
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
            "Create a calendar event called '[1b test] MCP verification event' "
            "tomorrow at 9am for 30 minutes."
        )
        logger.info("TEST | calendar | step=1 | response=%r", result.output)
        print(f"\nStep 1 — Create\n  Agent: {result.output}")
        print("  → Open Google Calendar and confirm the event appears tomorrow at 9am.")
        input("  Press Enter when confirmed...\n")

        # Step 2 — Update
        logger.info("TEST | calendar | step=2 | update")
        result = await agent.run(
            "Update the event '[1b test] MCP verification event'. "
            "Add the description: Created by test_mcp_calendar.py — safe to delete."
        )
        logger.info("TEST | calendar | step=2 | response=%r", result.output)
        print(f"Step 2 — Update\n  Agent: {result.output}")
        print("  → Confirm the description updated in Google Calendar.")
        print("  → Delete the event manually when done.")
        input("  Press Enter when confirmed...\n")

    print("Calendar test complete.")


if __name__ == "__main__":
    asyncio.run(run())
```

---

## 11. `tests/test_mcp_gmail.py`

```python
"""Stage 1b — Gmail MCP verification.

Run with: python -m tests.test_mcp_gmail

Requires TEST_EMAIL_ADDRESS in .env — the address to send the test email to.
Use your own email address. Check your inbox after the test.
"""

import asyncio
import logging
import os
from pydantic_ai import Agent
from app.core.llm_factory import LLMFactory
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
            f"Send an email to {test_email} with the subject "
            "'[1b test] MCP Gmail verification' and the body "
            "'This email was sent by test_mcp_gmail.py — safe to delete.'"
        )
        logger.info("TEST | gmail | step=1 | response=%r", result.output)
        print(f"\nStep 1 — Send\n  Agent: {result.output}")
        print(f"  → Check your inbox at {test_email}.")
        input("  Press Enter when confirmed...\n")

    print("Gmail test complete.")


if __name__ == "__main__":
    asyncio.run(run())
```

---

## 12. Updated `.env`

Add these to your existing `.env` (do not remove existing keys):

```
# gws Google Workspace CLI credentials
GOOGLE_WORKSPACE_CLI_CLIENT_ID=your-client-id.apps.googleusercontent.com
GOOGLE_WORKSPACE_CLI_CLIENT_SECRET=your-client-secret

# Test email address for Gmail test
TEST_EMAIL_ADDRESS=you@gmail.com
```

---

## 13. `requirements.txt` changes

No new Python packages are required. `gws` is a system binary installed via
npm, not a Python package. Your existing `pydantic-ai` and `mcp` packages
handle the MCP protocol.

Add a comment to `requirements.txt` documenting the system dependency:

```
# System dependency (not pip): gws CLI
# Install with: npm install -g @googleworkspace/cli
# Auth setup: gws auth login (one-time, see SPECIFICATION_1B_v2.md)
```

---

## 14. Implementation Sequence

**Step 1 — Complete all of Section 3 (Pre-Code Setup)**
Every verification command must pass before writing any code. Do not skip.

**Step 2 — Create folder structure**
```powershell
mkdir -Force app\mcp
New-Item -Force app\mcp\__init__.py
New-Item -Force tests\__init__.py
```

**Step 3 — Implement `app/mcp/google.py` and `app/mcp/__init__.py`**
Exactly as specified in Sections 7 and 6.

**Step 4 — Optional: run `scratch_list_tools.py`**
```powershell
python -m tests.scratch_list_tools
```
Prints all available tools for each service. Useful for understanding what
the LLM has to work with. Delete the file after.

**Step 5 — Run `test_mcp_tasks.py`**
```powershell
python -m tests.test_mcp_tasks
```
Pause after each step and confirm the result in Google Tasks.

**Step 6 — Run `test_mcp_calendar.py`**
```powershell
python -m tests.test_mcp_calendar
```
Confirm the event appears in Google Calendar. Delete it manually after.

**Step 7 — Run `test_mcp_gmail.py`**
Set `TEST_EMAIL_ADDRESS` in `.env` first.
```powershell
python -m tests.test_mcp_gmail
```
Check your inbox.

---

## 15. Troubleshooting

**`gws: command not found` after `npm install -g`**
Close and reopen PowerShell. npm global binaries are only on PATH in new
shell sessions. If still missing: `npm config get prefix` and add that path
to your system PATH manually.

**`gws` found in PowerShell but `shutil.which("gws")` returns None in Python**
Your IDE or Python process has a different PATH than your shell. The wrapper
uses `shutil.which` and raises a `RuntimeError` with instructions. Fix: add
the npm global bin directory to your system PATH (not just your shell session).
On Windows: System Properties → Environment Variables → Path → add the folder.

**`403 accessNotConfigured` when running terminal verification commands**
The API is not enabled in your GCP project. `gws` will print the exact URL.
Click it, enable the API, wait 30 seconds, retry.

**`gws auth login` opens browser but returns an error**
Make sure `GOOGLE_WORKSPACE_CLI_CLIENT_ID` and
`GOOGLE_WORKSPACE_CLI_CLIENT_SECRET` are set in your PowerShell session
(Step 5). If they are set and it still fails, check that your OAuth client
type is **Desktop app** (not Web application) in Cloud Console.

**Agent responds but nothing appears in Google**
The LLM called a tool but the result did not land. Check `logs/assistant.log`
for the full agent exchange. Run `scratch_list_tools.py` to confirm the tool
list is what you expect. Rephrase the instruction more explicitly.

**`gws mcp` starts but agent says it cannot complete the task**
The tool exists but the LLM could not construct valid arguments. Check
`scratch_list_tools.py` output to see exact tool names and parameters.
Simplify the instruction to match the tool's apparent purpose more closely.

**On Windows: JSON params with single quotes fail**
Windows CMD does not support single-quoted JSON. Use escaped double quotes:
`--params "{\"pageSize\": 5}"`. In Python this is handled automatically by
`MCPServerStdio` — you do not write shell commands from Python.

---

## 16. Production and Docker (reference — not built this stage)

`gws` stores credentials encrypted in the OS keyring at:
```
C:\Users\liang\AppData\Roaming\gws\credentials.enc  (Windows)
~/.local/share/gws/credentials.enc                   (Linux/VPS)
```

For production deployment on Linux VPS:
1. Install `gws` on the VPS: `npm install -g @googleworkspace/cli`
2. Set env vars and run `gws auth login` once via SSH (browser flow)
3. Mount the credentials file as a Docker volume:

```yaml
# docker-compose.yml (Stage 2+)
volumes:
  - ~/.local/share/gws:/root/.local/share/gws
```

Or copy credentials from local to VPS after auth:
```bash
scp -r ~/.local/share/gws/ user@your-vps:~/.local/share/gws/
```

One auth per environment. After that, fully silent and automatic.

---

## 17. How Stage 1c Wires These to Agents

Nothing changes in `app/mcp/`. The same function, different service lists:

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

## 18. Done When

- Section 3 (Pre-Code Setup) fully complete — all terminal verification
  commands return valid JSON
- `python -m tests.test_mcp_tasks` completes all three steps; task appears
  in Google Tasks after create, title updates correctly, task is gone after delete
- `python -m tests.test_mcp_calendar` completes both steps; event appears in
  Google Calendar at the correct time, description updates correctly
- `python -m tests.test_mcp_gmail` completes; email arrives in inbox with
  correct subject and body
- In all three tests, the agent response describes what it actually did —
  not just an echo of the instruction — confirming the LLM used a real tool
  and got a real result
- All test runs produce log lines in `logs/assistant.log`
- `from app.mcp import google_workspace_server` imports cleanly
- No Supervisor, no Telegram, no Redis — single-agent MCP verification only