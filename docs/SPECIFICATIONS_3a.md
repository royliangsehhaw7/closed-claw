# Personal Telegram Assistant
## Specification — Stage 3a: Agent Architecture

> **Assumes:** Stage 2 complete and merged to `main` — Telegram messages arrive
> via webhook, the agent loop runs, replies are sent, every exchange written to
> SQLite. `SupervisorAgent`, `SpecialistAgent` (tasks, calendar, email),
> `core/registry.py`, and the FastAPI gateway are all stable. Docker image builds
> and runs correctly.
>
> **Branch:** `stage/3a` branched from `main` after Stage 2 merge
>
> **Done when:** The registry builds itself by scanning `skills/` for MCP agents
> (tasks, calendar, email) and holding the reminder agent as a hardcoded tool
> agent. Each agent loads its behavioural instructions from its own `SKILL.md`.
> `workspace-mcp` starts once at app startup and is shared across all requests.
> The full Telegram flow works identically to Stage 2 — no behaviour changes,
> only structural ones.

---

## 1. What Stage 3a Adds

Stage 2 delivered a working gateway. The agent loop is proven end-to-end. The
next question is not whether the system works — it does — but whether it can grow
without code changes every time something needs to change.

Right now three things require a code edit, a commit, and a redeploy:

- Adding a new MCP specialist agent (hardcoded in `core/registry.py`)
- Changing how a specialist behaves (strings inside `_build_system_prompt()`)
- The MCP server cold start on every fresh container (spawned per request)

Stage 3a fixes all three, and introduces the reminder agent as the first
tool agent — a new specialist distinct from `workspace-mcp` that demonstrates
both agent types working together in the same registry.

New pieces introduced this stage:

- **`skills/`** — top-level folder; one subfolder per MCP agent, each containing
  a `SKILL.md` that fully describes the agent
- **`agents/reminders.py`** — new tool agent; Python functions for create, list,
  and delete reminders stored in a local SQLite table
- **Hybrid registry** — `core/registry.py` rewritten to hold hardcoded tool
  agents (reminders) and discover MCP agents by scanning `skills/` at startup
- **`core/skill_loader.py`** — reads and parses `SKILL.md` files; used by the
  registry at startup
- **Persistent MCP server** — `workspace-mcp` started once in the FastAPI
  lifespan handler and shared across all requests via `mcps/mcp_pool.py`

---

## 2. Two Agent Types

Stage 3a makes the distinction between agent types explicit and structural.

**MCP agents** delegate all tool execution to an external MCP server. They can
be fully described in a `SKILL.md` file — their key, name, which MCP server they
connect to, and their behavioural instructions. The registry can construct them
from that file alone. Tasks, calendar, and email are all MCP agents. They live in
`skills/` and are discovered at startup. Adding a new MCP agent requires no code
change.

**Tool agents** call deterministic Python functions directly. Those functions
must exist in code — a file can reference them but cannot contain them. Tool
agents are hardcoded in the registry. Their behavioural instructions still live
in a `SKILL.md` like any other agent, but their wiring requires Python.

The reminder agent is the first and only tool agent in Stage 3a. It is
hardcoded because its Python functions (`create_reminder`, `list_reminders`,
`delete_reminder`) must be bound at construction time. Its `SKILL.md` governs
its behaviour — what it says, how it confirms, what it asks — exactly the same
as the MCP agents.

This distinction is permanent. It is not a limitation to be solved later — it
reflects a real architectural boundary between agents that own their own tool
implementations and agents that delegate to external servers.

---

## 3. Why the Reminder Agent Belongs in Stage 3a

The reminder agent is introduced here rather than later for one reason: Stage 3a
is the stage where the registry is rewritten. The hybrid construction logic —
hardcoded tool agents plus discovered MCP agents — needs a concrete tool agent
to demonstrate and validate the pattern. Without one, the hardcoded path exists
in code but is never exercised.

The reminder agent is also genuinely useful as a personal assistant feature. It
is deliberately scoped to store-and-retrieve only in this stage — no scheduler,
no proactive Telegram messages. Proactive firing requires background
infrastructure (a scheduler running in lifespan) that belongs in Stage 4
alongside Redis and PostgreSQL. Stage 3a gets the agent wired correctly; Stage 4
makes it active.

---

## 4. Why These Items Belong Together

Persistent MCP, skills, hybrid registry, and the reminder agent are not
independent features. They share a single wiring point — app startup — and each
depends on the previous:

1. `workspace-mcp` must be running before MCP agents can be constructed
2. `SKILL.md` files must be parsed before agents can be constructed from them
3. The registry must be complete before the supervisor can be constructed
4. The supervisor must be constructed before the gateway can handle requests

Implementing any one of these without the others leaves the startup sequence
incomplete. They are one piece of work.

---

## 5. Why Skills Replace Hardcoded System Prompt Strings

Each specialist agent currently builds its system prompt by assembling strings
inside `_build_system_prompt()`. This works while those strings are short. As
the assistant matures — learning formatting preferences, edge case handling,
personal quirks — those strings grow. Each edit is a code change.

Skills move behavioural instructions out of Python and into markdown. The agent
reads its `SKILL.md` at startup and injects the content into its system prompt.
Editing agent behaviour becomes editing a text file — no code change, no commit,
no redeploy. On the next restart the agent behaves differently.

The important detail: **full skill content is not blindly dumped into the system
prompt at startup**. At startup the agent injects only the skill's name and
one-line description. The full instructions are loaded on demand when the skill
is relevant to the current request. Token cost stays flat regardless of how many
skills exist. This is the same pattern OpenClaw uses and the correct foundation
for a system that will gain more agents over time.

---

## 6. Why the Persistent MCP Server Belongs in This Stage

In Stage 2, `workspace-mcp` is spawned as a subprocess on the first tool call
of each request. On a fresh container the first call takes 10–20 seconds while
`uvx` fetches and caches the package. The Stage 2 troubleshooting section already
flags this as a known limitation.

Stage 3a fixes it by promoting `workspace-mcp` to a process-level singleton.
It starts once in the lifespan handler and is shared across all requests and all
MCP agents. The `mcps/mcp_pool.py` foundation from Stage 1d — `get_pool_server()`
— is already in place. Stage 3a wires it into lifespan.

This belongs here because the hybrid registry needs a running MCP server to
construct MCP agents at startup. The persistent server is therefore the first
thing initialised in lifespan, before the registry runs.

---

## 7. `SKILL.md` Format

Each skill file is plain markdown with a YAML frontmatter block. The frontmatter
is machine-readable — parsed by `core/skill_loader.py` at startup. The markdown
body is human-readable — injected into the agent's system prompt on demand.

```markdown
---
key: calendar
name: Calendar Agent
type: mcp
mcp_server: workspace-mcp
description: Creates and manages Google Calendar events from natural language.
---

## Behaviour

- Always confirm the date, time, and title before creating an event.
- If the user does not specify a time, ask — never assume.
- Default duration is 1 hour unless stated otherwise.
- Use the user's local timezone (injected from memory at startup in Stage 3b).
- When an event is created, confirm with: date, time, title, and calendar name.

## Edge Cases

- Ambiguous dates ("next Friday", "end of month") — restate your interpretation
  before acting, e.g. "I'll set that for Friday 6 June — confirm?"
- Overlapping events — warn the user if a conflict is detected.
- Past dates — confirm explicitly before creating.
```

**Frontmatter fields:**

| Field | Required | Description |
|---|---|---|
| `key` | yes | Unique agent identifier. Used for registry lookup and deduplication. |
| `name` | yes | Human-readable display name. |
| `type` | yes | `mcp` or `tool`. Registry uses this to determine construction path. |
| `mcp_server` | if `type: mcp` | Name of the MCP server this agent connects to. |
| `description` | yes | One-line summary. Injected into supervisor context. |

The markdown body has no required structure. Write it as instructions to the
agent — whatever makes the behaviour clearer and more correct.

Tool agents also have a `SKILL.md`. The frontmatter declares `type: tool` and
omits `mcp_server`. The markdown body is injected into the agent's system prompt
identically to MCP agents.

---

## 8. Hybrid Registry — How It Works

`core/registry.py` is rewritten. The public interface — `get_agent(key)`,
`list_agents()` — does not change. The supervisor calls the registry identically
to Stage 2. Only the internal construction logic changes.

### Startup sequence

```
lifespan handler
    │
    ├── 1. Start persistent MCP server (mcps/mcp_pool.py)
    │         workspace-mcp started once, shared across all MCP agents
    │
    ├── 2. Build registry
    │         │
    │         ├── a. Construct hardcoded tool agents
    │         │         reminders → RemindersAgent (SQLite, Python functions)
    │         │         loads skills/reminders/SKILL.md for instructions
    │         │
    │         ├── b. Scan skills/ folder
    │         │         for each SKILL.md found:
    │         │           - skip if key already in registry (deduplication)
    │         │           - skip with warning if type: tool (no Python to bind)
    │         │           - construct MCP agent if type: mcp
    │         │         tasks    → TasksAgent    (MCP: workspace-mcp)
    │         │         calendar → CalendarAgent  (MCP: workspace-mcp)
    │         │         email    → EmailAgent     (MCP: workspace-mcp)
    │         │
    │         └── c. Registry ready — full agent set available
    │                 reminders, tasks, calendar, email
    │                 + any additional MCP agents found in skills/
    │
    └── 3. Construct SupervisorAgent with completed registry
```

### Deduplication rule

If a `SKILL.md` in `skills/` has a `key` that matches a hardcoded agent, the
file is **not** used for construction (the hardcoded agent wins) but its markdown
body **is** loaded as the agent's behavioural instructions. A hardcoded agent's
behaviour can be tuned by editing its `SKILL.md` without touching Python.

### Adding a new MCP agent (no code required)

```
skills/
  new_agent/
    SKILL.md     ← type: mcp, mcp_server: some-mcp-server
```

Restart the app. The registry scans, finds the new entry, constructs the agent,
adds it to the set. The supervisor sees it immediately.

---

## 9. Reminder Agent

The reminder agent is a tool agent. It manages a `reminders` table in the
existing SQLite database. It has no connection to `workspace-mcp` — it is
entirely self-contained.

### Tools

```python
async def create_reminder(text: str, remind_at: datetime) -> Reminder:
    """Store a new reminder. Returns the created record."""

async def list_reminders(include_past: bool = False) -> list[Reminder]:
    """Return upcoming reminders. Pass include_past=True to see all."""

async def delete_reminder(reminder_id: int) -> bool:
    """Delete a reminder by ID. Returns True if found and deleted."""
```

### SQLite schema

```sql
CREATE TABLE IF NOT EXISTS reminders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    text       TEXT    NOT NULL,
    remind_at  TEXT    NOT NULL,  -- ISO 8601 UTC
    created_at TEXT    NOT NULL,
    fired      INTEGER NOT NULL DEFAULT 0
);
```

`fired` is included now and set to 0. Stage 4 will use it when the scheduler
marks reminders as sent. Adding it now avoids a schema migration later.

### Scope in Stage 3a

The reminder agent stores and retrieves. It does not fire. When you ask
"remind me to call David at 3pm tomorrow" the agent creates a record and
confirms the time. When you ask "what reminders do I have?" it lists them.
Nothing sends a Telegram message at 3pm — that is Stage 4.

---

## 10. Architecture

```
FastAPI lifespan (startup)
    │
    ├── mcps/mcp_pool.py → workspace-mcp (persistent subprocess, shared)
    │
    └── core/registry.py
              │
              ├── Hardcoded tool agents
              │       reminders → RemindersAgent (SQLite + Python functions)
              │                   loads skills/reminders/SKILL.md
              │
              └── skills/ scan → MCP agents constructed and added
                      tasks    → TasksAgent    (workspace-mcp)
                      calendar → CalendarAgent  (workspace-mcp)
                      email    → EmailAgent     (workspace-mcp)
                      + any future MCP agents dropped into skills/

Telegram webhook (per request)
    │
    └── SupervisorAgent.run(text, deps)
              │
              └── registry.get_agent(key)
                      │
                      ├── MCP agents  → persistent workspace-mcp
                      │                   → Google Tasks / Calendar / Gmail
                      │
                      └── Tool agents → Python functions → SQLite
```

---

## 11. Project Structure — Stage 3a Changes

Only new and modified files are listed.

```
project/
├── skills/
│   ├── tasks/
│   │   └── SKILL.md                 # NEW — tasks agent behavioural instructions
│   ├── calendar/
│   │   └── SKILL.md                 # NEW — calendar agent behavioural instructions
│   ├── email/
│   │   └── SKILL.md                 # NEW — email agent behavioural instructions
│   └── reminders/
│       └── SKILL.md                 # NEW — reminders agent behavioural instructions
│
├── agents/
│   └── reminders.py                 # NEW — RemindersAgent, tool functions, schema
│
├── core/
│   ├── registry.py                  # REWRITTEN — hybrid construction + skills scan
│   └── skill_loader.py              # NEW — parses SKILL.md frontmatter and body
│
├── mcps/
│   └── mcp_pool.py                  # UPDATED — promoted to lifespan singleton
│
└── gateway/
    └── app.py                       # UPDATED — lifespan starts MCP server first,
                                     #           then builds registry
```

Existing agent files (`agents/tasks.py`, `agents/calendar.py`,
`agents/email.py`) are not deleted and their Python mechanics are not touched.
Their `_build_system_prompt()` methods gain a new input source — the `SKILL.md`
body — but the construction logic otherwise stays the same. These agents are now
constructed by the registry from their `SKILL.md` rather than hardcoded, but
their internal implementation is unchanged.

---

## 12. `core/skill_loader.py`

Responsible for one thing: reading a `SKILL.md` file and returning its parsed
contents. Used by the registry at startup. Not used at request time.

```python
from dataclasses import dataclass
from pathlib import Path
import yaml

@dataclass
class SkillMeta:
    key: str
    name: str
    type: str                  # "mcp" or "tool"
    mcp_server: str | None     # None for tool agents
    description: str
    instructions: str          # full markdown body, loaded on demand

def load_skill(path: Path) -> SkillMeta:
    """Parse a SKILL.md file. Raises ValueError on missing required fields."""
    ...

def scan_skills_dir(skills_dir: Path) -> dict[str, SkillMeta]:
    """Scan skills/ folder. Returns {key: SkillMeta} for all valid entries."""
    ...
```

`load_skill` splits the file at the YAML frontmatter delimiters (`---`), parses
the frontmatter block with `pyyaml`, and returns the markdown body as
`instructions`. Any file missing required frontmatter fields logs a warning and
is skipped — a malformed skill file must not crash startup.

---

## 13. Updated `requirements.txt`

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

# Stage 3a
pyyaml
```

`pyyaml` is the only new dependency. It parses the YAML frontmatter in
`SKILL.md` files.

---

## 14. Implementation Phases

Each phase must be fully validated before moving to the next.

**Phase 1 — Persistent MCP server**

Wire `mcps/mcp_pool.py` into the FastAPI lifespan handler. `workspace-mcp`
starts at app startup and shuts down cleanly on app shutdown. All MCP specialist
agents use the shared server instance. Remove any per-request subprocess
spawning.

Pass/fail: app starts and logs `mcp_pool | workspace-mcp started`. First tool
call completes without the 10–20 second cold start. Telegram flow works
identically to Stage 2.

**Phase 2 — Skill files and loader**

Create `skills/tasks/SKILL.md`, `skills/calendar/SKILL.md`,
`skills/email/SKILL.md`, `skills/reminders/SKILL.md`. Write behavioural
instructions for each. Implement `core/skill_loader.py`. Write unit tests
covering valid files, missing fields, and malformed YAML.

Pass/fail: `skill_loader` tests pass. All four `SKILL.md` files load without
error. `scan_skills_dir` returns three entries (tasks, calendar, email —
reminders is a tool agent and is not in `skills/` scan path... see note below).

> **Note:** `skills/reminders/SKILL.md` exists for behavioural instructions but
> the reminder agent is hardcoded. The registry loads its instructions from the
> file but does not construct it from the file. `scan_skills_dir` will find it
> and skip it (key already in registry via hardcoded path).

**Phase 3 — Reminder agent**

Implement `agents/reminders.py`. Create the `reminders` SQLite table in the
existing database initialisation path. Wire the three tool functions into the
agent. Add `RemindersAgent` to the hardcoded base set in the rewritten registry.

Pass/fail: `python main.py` CLI — "remind me to call David tomorrow at 3pm"
creates a record. "What reminders do I have?" lists it. "Delete reminder 1"
removes it. SQLite table confirms correct state after each operation.

**Phase 4 — Hybrid registry**

Rewrite `core/registry.py`. Hardcoded tool agents constructed first (reminders).
Skill loader scans `skills/` and constructs MCP agents (tasks, calendar, email).
Deduplication applied. Supervisor constructed with completed registry.

Pass/fail: registry builds at startup with all four agents. Startup logs show
correct sequence. A dummy `skills/test_agent/SKILL.md` with `type: mcp` is
discovered and logged as appended. Remove after testing.

**Phase 5 — Full integration test**

Restart the app. Confirm startup log sequence: MCP server starts, skill files
load, registry builds (tool agents first, then MCP agents from scan), supervisor
initialises. Run full Telegram smoke test. Confirm all Stage 2 behaviour is
unchanged. Confirm reminder operations work via Telegram.

Pass/fail: all Stage 2 smoke tests pass. Reminder create, list, and delete work
via Telegram. `python main.py` CLI loop still works.

---

## 15. Validation Steps

**Step 1 — Confirm persistent MCP server starts**
```powershell
uvicorn gateway.app:app --reload
```
Expected log line:
```
mcp_pool | workspace-mcp started pid=<n>
```

**Step 2 — Confirm cold start is gone**

Send a task creation message immediately after a fresh app start. Time the
response. Expected: under 3 seconds.

**Step 3 — Confirm skill files load**

Expected log lines at startup:
```
skill_loader | loaded skills/tasks/SKILL.md
skill_loader | loaded skills/calendar/SKILL.md
skill_loader | loaded skills/email/SKILL.md
skill_loader | loaded skills/reminders/SKILL.md
```

**Step 4 — Confirm registry builds correctly**

Expected log lines:
```
registry | tool agent registered (hardcoded): reminders
registry | mcp agent registered (skills scan): tasks
registry | mcp agent registered (skills scan): calendar
registry | mcp agent registered (skills scan): email
registry | build complete — 4 agents registered
```

**Step 5 — Confirm new MCP agent discovery**

Create `skills/test_agent/SKILL.md` with `type: mcp` and a valid `mcp_server`
field. Restart. Expected:
```
registry | mcp agent registered (skills scan): test_agent
registry | build complete — 5 agents registered
```

Remove the folder. Restart. Confirm registry returns to 4 agents.

**Step 6 — Reminder agent smoke test (CLI)**
```powershell
python main.py
```

| Input | Expected |
|---|---|
| `Remind me to call David tomorrow at 3pm` | Reminder created, confirmation with date and time |
| `What reminders do I have?` | Lists the reminder with ID, text, and time |
| `Delete reminder 1` | Confirmed deleted |
| `What reminders do I have?` | Empty list |

**Step 7 — Full Telegram smoke test**

| Message | Expected |
|---|---|
| `What can you help me with?` | Reply in Telegram, no tool call |
| `Add a task called Review report due this Friday` | Task in Google Tasks, calendar event, confirmation |
| `Send an email to your@gmail.com subject Stage 3a test body Agent architecture complete` | Email delivered, confirmation |
| `Remind me to review the budget next Monday at 9am` | Reminder stored, confirmation with date and time |
| `What reminders do I have?` | Lists the reminder |
| `/start` | `Assistant ready. Send me a message.` |

---

## 16. Troubleshooting

**MCP server fails to start at lifespan**
Confirm `workspace-mcp` credentials are available — same volume mount or disk
path as Stage 2. The persistent server requires credentials at startup, not at
first tool call. If credentials are missing the app starts but the first MCP
tool call fails with an auth error.

**Skill file not loaded**
Confirm the file is named exactly `SKILL.md` (case-sensitive on Linux). Confirm
YAML frontmatter is delimited with `---` on its own line at the top and after the
last frontmatter field. Any YAML parse error causes the file to be skipped with
a warning — check logs.

**MCP agent in skills/ not discovered**
Confirm `type: mcp` is set in frontmatter. `type: tool` entries are skipped with
a warning. Confirm the `key` does not match an existing hardcoded agent —
deduplication means construction is skipped (instructions still loaded).

**Reminder agent not found by supervisor**
Confirm `RemindersAgent` is in the hardcoded base set in the rewritten
`core/registry.py`. The reminder agent does not come from `skills/` scan — it
must be explicitly constructed in the hardcoded path.

**Stage 2 Telegram flow broken after registry rewrite**
The registry's public interface (`get_agent`, `list_agents`) must not change.
Confirm all four agents are registered under their original keys (`tasks`,
`calendar`, `email`, `reminders`). The supervisor calls the registry identically
to Stage 2.

**SQLite schema error on reminders**
Confirm the `reminders` table creation runs in the same database initialisation
path as `agent_turns`. Both tables must exist in the same SQLite file at the
path set by `SQLITE_PATH` in `.env`.

---

## 17. How Stage 3b Builds on This

Stage 3a establishes how agents are built and discovered. The registry is
complete. The persistent MCP server is running. Skill instructions are loaded.

Stage 3b enriches those agents with knowledge about who they are and who they
are talking to. Two markdown files are loaded at startup and injected into agent
system prompts alongside the skill instructions:

- `memory/agents/<key>.md` — the agent's persona: tone, style, boundaries
- `memory/brain/user.md` — facts about you: timezone, preferences, contact
  shortcuts

Stage 3b adds one new loader (`memory/markdown_store.py`) and one new injection
point in `_build_system_prompt()`. The registry, skill loader, and persistent
MCP server do not change.

---

## 18. Done When

- App starts and logs MCP server start, skill file loads, and registry build
  in correct sequence
- `workspace-mcp` cold start is eliminated — first tool call under 3 seconds
  on a fresh app start
- All four agents registered: reminders (hardcoded tool), tasks, calendar,
  email (discovered MCP)
- Each agent has a `SKILL.md` with behavioural instructions
- A new `SKILL.md` with `type: mcp` dropped into `skills/` is discovered and
  appended without any code change
- Reminder create, list, and delete work via both CLI and Telegram
- All Stage 2 smoke tests pass unchanged
- `python main.py` CLI loop still works