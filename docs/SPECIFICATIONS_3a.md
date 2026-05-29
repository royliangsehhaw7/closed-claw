# Personal Telegram Assistant
## Specification — Stage 3a: Agent Architecture

> **Assumes:** Stage 2 complete and merged to `main` — Telegram messages arrive
> via webhook, the FastAPI gateway runs, the agent loop executes, replies are sent,
> every exchange written to SQLite `agent_turns`. `SupervisorAgent`,
> `SpecialistAgent` (tasks, calendar, email), `core/registry.py`, and the Docker
> image are all stable. `python main.py` CLI loop still works.
>
> **Branch:** `stage/3a` branched from `main` after Stage 2 merge
>
> **Done when:** The registry builds itself at startup by scanning `skills/` for
> MCP agents and holding the reminder agent as a hardcoded tool agent. Each agent
> loads its behavioural instructions from its own `SKILL.md`. `workspace-mcp`
> starts once in the FastAPI lifespan handler and is shared across all requests.
> The full Telegram flow works identically to Stage 2 — no behaviour changes,
> only structural ones. The reminder agent creates, lists, and deletes reminders
> via both CLI and Telegram.

---

## 1. What Stage 3a Adds

Stage 2 delivered a working Telegram gateway. The agent loop is proven end-to-end.
The question for Stage 3a is not whether the system works — it does — but whether
it can grow without touching Python every time something needs to change.

Right now three things require a code edit, a commit, and a redeploy:

- **Adding a new MCP specialist** — hardcoded in `core/registry.py`
- **Changing how a specialist behaves** — strings embedded inside `_build_system_prompt()`
- **Cold start on first tool call** — `workspace-mcp` is spawned as a subprocess
  per request; on a fresh container this takes 10–20 seconds

Stage 3a fixes all three. It also introduces the first **tool agent** — the
reminder agent — which demonstrates both agent types working together in the same
registry and gives the assistant a genuinely useful new capability.

**What changes at the code level:**

| File | Change |
|---|---|
| `skills/tasks/SKILL.md` | NEW — tasks agent behavioural instructions |
| `skills/calendar/SKILL.md` | NEW — calendar agent behavioural instructions |
| `skills/email/SKILL.md` | NEW — email agent behavioural instructions |
| `skills/reminders/SKILL.md` | NEW — reminders agent behavioural instructions |
| `agents/reminders.py` | NEW — RemindersAgent, tool functions, schema creation |
| `core/skill_loader.py` | NEW — SKILL.md parser |
| `core/registry.py` | REWRITTEN — hybrid construction + skills scan |
| `mcps/mcp_pool.py` | UPDATED — promoted to lifespan singleton |
| `gateway/app.py` | UPDATED — lifespan starts MCP server, then builds registry |

**What does not change:**

`agents/tasks.py`, `agents/calendar.py`, `agents/email.py` — their Python
mechanics are untouched. Their `_build_system_prompt()` gains a new input
(the `SKILL.md` body) but the construction logic is the same. `SupervisorAgent`,
`AgentDeps`, `SQLiteStore`, `TurnRecord`, `schemas/`, `memory/sqlite_store.py`,
`gateway/telegram_client.py` — none of these are touched.

---

## 2. Two Agent Types

Stage 3a makes the distinction between agent types explicit and structural. This
distinction is permanent — it reflects a real architectural boundary.

### MCP agents

An MCP agent delegates all tool execution to an external MCP server. It has no
Python tool functions of its own. Everything it can do is expressed through MCP
tool calls to the connected server.

Because an MCP agent needs only a server name and behavioural instructions to
function, it can be fully described in a `SKILL.md` file. The registry reads that
file, looks up the running MCP server by name, and constructs the agent — no
Python required. Tasks, calendar, and email are all MCP agents.

**Adding a new MCP agent: create `skills/<key>/SKILL.md`, restart. That is all.**

### Tool agents

A tool agent calls deterministic Python functions directly. Those functions must
exist in code — a file can describe them but cannot contain them. The registry
constructs tool agents from hardcoded Python, not from a scan.

Tool agents still have a `SKILL.md` that governs their behaviour — what they say,
how they confirm, what they ask. The only difference is that the registry does
not construct them from the file; it constructs them from Python and then reads
the file for behavioural instructions.

The reminder agent is the first and only tool agent in Stage 3a.

---

## 3. Why the Persistent MCP Server Changes Things

In Stage 2, `workspace-mcp` was spawned as a subprocess on the first tool call
of each request. This meant:

1. The first tool call after a container restart took 10–20 seconds while `uvx`
   fetched and started the package.
2. Every SpecialistAgent constructed its own subprocess reference.
3. If two messages arrived in quick succession, both could race to spawn the MCP
   server.

Stage 3a promotes `workspace-mcp` to a process-level singleton: it is started
once in the FastAPI lifespan handler and shared across all requests and all MCP
agents. The `mcps/mcp_pool.py` module from Stage 1d already contains the
`get_pool_server()` function — Stage 3a wires it into lifespan.

This change has a structural consequence: the persistent server must be running
**before** the registry constructs MCP agents, because each MCP agent receives a
reference to the shared server at construction time. The lifespan startup
sequence is therefore strictly ordered:

```
1. Start workspace-mcp (persistent subprocess)
2. Build registry (which constructs agents that hold a reference to that subprocess)
3. Construct SupervisorAgent with the completed registry
```

Inverting this order causes startup failures. The spec enforces the order
explicitly.

---

## 4. Startup Sequence — Full Detail

This is the exact order of operations in the updated `gateway/app.py` lifespan
handler. Each step depends on the previous.

```
FastAPI lifespan (startup)
│
├── 1. Validate environment
│         USER_GOOGLE_EMAIL, WEBHOOK_SECRET, TELEGRAM_CHAT_ID must all be set.
│         Raise RuntimeError immediately if any are missing.
│         This is unchanged from Stage 2.
│
├── 2. Delete pending Telegram updates
│         Call deleteWebhook?drop_pending_updates=true.
│         Prevents message flood on restart. Unchanged from Stage 2.
│
├── 3. Initialise SQLiteStore
│         Creates the database and all tables including the new `reminders` table.
│         Unchanged from Stage 2 except the reminders table is now created here.
│
├── 4. Start workspace-mcp (NEW in Stage 3a)
│         Calls mcps/mcp_pool.py → get_pool_server("workspace-mcp")
│         Starts workspace-mcp as a persistent subprocess.
│         Waits for the server to be ready before proceeding.
│         Logs: mcp_pool | workspace-mcp started pid=<n>
│
├── 5. Build registry (NEW in Stage 3a — was simpler in Stage 2)
│         Calls core/registry.py → build_registry(mcp_server)
│         Passes the running MCP server reference in.
│         Registry constructs:
│           a. Hardcoded tool agents (reminders)
│           b. MCP agents from skills/ scan (tasks, calendar, email)
│         Logs: registry | build complete — 4 agents registered
│
└── 6. Construct SupervisorAgent
          Receives the completed registry.
          Unchanged from Stage 2.
```

**Shutdown (unchanged from Stage 2 except MCP server teardown):**

```
FastAPI lifespan (shutdown)
├── SupervisorAgent cleanup (if any)
├── workspace-mcp subprocess terminate + wait
└── Log: gateway | shutdown
```

---

## 5. SKILL.md Format — Full Specification

Every agent has a `SKILL.md` file under `skills/<key>/SKILL.md`. The file has
two parts: a YAML frontmatter block and a markdown body.

### Frontmatter

The frontmatter is delimited by `---` on its own line at the top of the file and
after the last field. It is machine-readable — parsed by `core/skill_loader.py`.

```
---
key: <string>
name: <string>
type: mcp | tool
mcp_server: <string>    # required if type is mcp, omit if type is tool
description: <string>   # one line only
---
```

| Field | Required | Type | Description |
|---|---|---|---|
| `key` | yes | string | Unique agent identifier. Used for registry lookup and deduplication. Must be lowercase, no spaces. |
| `name` | yes | string | Human-readable display name. Used in logs and supervisor context. |
| `type` | yes | `mcp` or `tool` | Registry uses this to determine construction path. `tool` entries in `skills/` are skipped with a warning — tool agents are hardcoded. |
| `mcp_server` | if `type: mcp` | string | The MCP server name this agent connects to. Must match the name used in `get_pool_server()`. |
| `description` | yes | string | One-line summary. Injected into the supervisor's routing context so it can decide which agent to call. |

### Markdown body

The body begins immediately after the closing `---` of the frontmatter. There is
no required structure — write it as instructions to the agent. This content is
injected into the agent's system prompt when the agent is active on a request.

**Important:** The body is **not** dumped into the system prompt at startup. At
startup the agent receives only the `name` and `description` from the frontmatter
(keeping the base prompt lean). The full body is loaded on demand when the agent
is relevant to the current request. This keeps token cost flat regardless of how
many skills exist.

### Example — `skills/calendar/SKILL.md`

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
- Confirm with: date, time, title, and calendar name after creation.

## Edge Cases

- Ambiguous dates ("next Friday", "end of month") — restate your interpretation
  before acting: "I'll set that for Friday 6 June — confirm?"
- Overlapping events — warn the user if a conflict is detected.
- Past dates — confirm explicitly before creating.
```

### Example — `skills/reminders/SKILL.md`

```markdown
---
key: reminders
name: Reminder Agent
type: tool
description: Stores and retrieves personal reminders with a date and time.
---

## Behaviour

- When storing a reminder, always confirm the exact text and the scheduled time.
- If the user does not specify a time, ask — never assume.
- When listing reminders, show each one with its ID, text, and scheduled time.
- When deleting, confirm the ID and text of what was deleted.
- In Stage 3a this agent stores and retrieves only. It does not send proactive
  Telegram messages. That is Stage 4.

## Edge Cases

- Ambiguous times ("tomorrow morning") — ask for clarification.
- If the user asks to delete a reminder that does not exist, say so clearly.
- If the reminders list is empty, say "You have no upcoming reminders."
```

---

## 6. `core/skill_loader.py` — Full Implementation

Responsible for one thing: reading a `SKILL.md` file and returning its parsed
contents. Used by the registry at startup only. Never called at request time.

A malformed skill file must not crash startup. If frontmatter is missing or
required fields are absent, the file is logged as a warning and skipped.

```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import yaml

logger = logging.getLogger("skill_loader")


@dataclass
class SkillMeta:
    key: str
    name: str
    type: str                  # "mcp" or "tool"
    mcp_server: str | None     # None for tool agents
    description: str
    instructions: str          # full markdown body, injected on demand


def load_skill(path: Path) -> SkillMeta | None:
    """Parse a SKILL.md file.

    Returns a SkillMeta if the file is valid, or None if it should be skipped.
    Logs a warning for every skipped file — silent failures are not acceptable.

    The file must begin with a YAML frontmatter block delimited by '---'.
    Any content after the second '---' is treated as the markdown body.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("skill_loader | cannot read %s: %s", path, exc)
        return None

    # Split on frontmatter delimiters.
    # A valid file looks like: "---\n<yaml>\n---\n<body>"
    # Split into at most 3 parts: ["", yaml_block, body]
    parts = raw.split("---", maxsplit=2)
    if len(parts) < 3:
        logger.warning(
            "skill_loader | %s: missing frontmatter delimiters — skipping", path
        )
        return None

    yaml_block = parts[1].strip()
    body = parts[2].strip()

    try:
        meta = yaml.safe_load(yaml_block)
    except yaml.YAMLError as exc:
        logger.warning("skill_loader | %s: YAML parse error: %s — skipping", path, exc)
        return None

    if not isinstance(meta, dict):
        logger.warning("skill_loader | %s: frontmatter is not a mapping — skipping", path)
        return None

    # Validate required fields.
    required = ("key", "name", "type", "description")
    missing = [f for f in required if not meta.get(f)]
    if missing:
        logger.warning(
            "skill_loader | %s: missing required fields %s — skipping", path, missing
        )
        return None

    skill_type = str(meta["type"]).lower()
    if skill_type not in ("mcp", "tool"):
        logger.warning(
            "skill_loader | %s: unknown type %r (expected 'mcp' or 'tool') — skipping",
            path, meta["type"],
        )
        return None

    mcp_server: str | None = meta.get("mcp_server") or None
    if skill_type == "mcp" and not mcp_server:
        logger.warning(
            "skill_loader | %s: type is 'mcp' but mcp_server is not set — skipping", path
        )
        return None

    skill = SkillMeta(
        key=str(meta["key"]).lower(),
        name=str(meta["name"]),
        type=skill_type,
        mcp_server=mcp_server,
        description=str(meta["description"]),
        instructions=body,
    )
    logger.info("skill_loader | loaded %s", path)
    return skill


def scan_skills_dir(skills_dir: Path) -> dict[str, SkillMeta]:
    """Scan the skills/ directory and return all valid SkillMeta entries.

    Each immediate subdirectory of skills_dir is expected to contain a SKILL.md.
    Subdirectories without a SKILL.md are silently skipped (they may contain
    supporting assets).

    Returns a dict keyed by skill.key. Duplicate keys (two folders with the same
    key frontmatter value) emit a warning; the first one found wins.
    """
    result: dict[str, SkillMeta] = {}

    if not skills_dir.is_dir():
        logger.warning(
            "skill_loader | skills dir %s does not exist — no skills loaded", skills_dir
        )
        return result

    for subdir in sorted(skills_dir.iterdir()):
        if not subdir.is_dir():
            continue
        skill_file = subdir / "SKILL.md"
        if not skill_file.exists():
            continue
        skill = load_skill(skill_file)
        if skill is None:
            continue
        if skill.key in result:
            logger.warning(
                "skill_loader | duplicate key %r in %s — first entry wins", skill.key, skill_file
            )
            continue
        result[skill.key] = skill

    return result
```

**Why `yaml.safe_load` and not `yaml.load`?** `yaml.load` can execute arbitrary
Python constructors embedded in the YAML. `safe_load` restricts parsing to basic
types only. Skill files may be edited by hand — safe parsing prevents a typo or
malicious edit from executing code at startup.

**Why log warnings instead of raising?** A broken skill file should degrade
gracefully — the agent it described does not exist, but all other agents still
work. Raising an exception would crash the entire app because of one broken file.
The developer sees the warning in logs and fixes the file.

---

## 7. `mcps/mcp_pool.py` — Updated for Persistent Singleton

In Stage 2, `mcp_pool.py` contained `get_pool_server()` as a foundation but it
was called per-request. Stage 3a promotes it to a lifespan singleton.

The key change: `get_pool_server()` is called once in `lifespan()`. The returned
server reference is stored as a module-level global and passed into
`build_registry()`. All MCP agents receive the same reference.

Below is the full updated file. Lines that change from Stage 2 are marked.

```python
from __future__ import annotations

import asyncio
import logging
from typing import Any

logger = logging.getLogger("mcp_pool")

# Module-level singleton — set once in lifespan, reused forever.
_server: Any | None = None   # NEW: module-level global


async def start_pool_server(server_name: str) -> Any:
    """Start workspace-mcp as a persistent subprocess.

    Called once in the FastAPI lifespan handler. Stores the running server
    reference in the module-level _server global.

    Args:
        server_name: The MCP server to start, e.g. "workspace-mcp".

    Returns:
        The running MCPServerStdio instance.

    Raises:
        RuntimeError if the server fails to start.
    """
    global _server

    # Import here to avoid circular imports at module load time.
    from pydantic_ai.mcp import MCPServerStdio

    logger.info("mcp_pool | starting %s ...", server_name)

    server = MCPServerStdio(
        "uvx",
        args=[server_name],
    )

    # MCPServerStdio must be started explicitly before it can accept tool calls.
    # This call starts the subprocess and waits for the server to signal readiness.
    await server.start()

    _server = server
    logger.info("mcp_pool | %s started", server_name)
    return server


async def stop_pool_server() -> None:
    """Terminate the persistent MCP server subprocess.

    Called in the FastAPI shutdown handler. Sends SIGTERM and waits for the
    process to exit cleanly.
    """
    global _server
    if _server is not None:
        logger.info("mcp_pool | stopping workspace-mcp ...")
        await _server.stop()
        _server = None
        logger.info("mcp_pool | workspace-mcp stopped")


def get_pool_server() -> Any:
    """Return the running MCP server reference.

    Called by the registry during startup and by agents at request time.
    Raises RuntimeError if called before start_pool_server().
    """
    if _server is None:
        raise RuntimeError(
            "mcp_pool.get_pool_server() called before start_pool_server(). "
            "The persistent MCP server must be started in lifespan before the "
            "registry is built."
        )
    return _server
```

**Why `await server.start()`?** `MCPServerStdio` from `pydantic-ai` is an async
context manager. In Stage 2 it was used with `async with` inside each agent run
— the server started when the context was entered and stopped when it exited.
Stage 3a calls `.start()` directly in lifespan and `.stop()` in shutdown,
bypassing the context manager. This is intentional — we want the server to
outlive any individual request.

**Why not use `async with MCPServerStdio(...)` at the module level?** Because an
`async with` block must be entered inside a coroutine. The module level is not
async. Lifespan is a coroutine, so it is the right place to enter persistent
async resources.

---

## 8. `core/registry.py` — Rewritten for Hybrid Construction

The public interface does not change. The `SupervisorAgent` still calls
`get_agent(key)` and `list_agents()` identically to Stage 2. Only the internal
construction logic changes.

```python
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from core.skill_loader import SkillMeta, scan_skills_dir

logger = logging.getLogger("registry")

# The agents/ modules are imported here. Their Python classes are constructed
# in build_registry() using the skill loader output and the MCP server reference.
from agents.reminders import RemindersAgent
from agents.tasks import TasksAgent
from agents.calendar import CalendarAgent
from agents.email import EmailAgent


class AgentRegistry:
    """Holds all registered specialist agents. Constructed once at startup."""

    def __init__(self) -> None:
        self._agents: dict[str, Any] = {}

    def register(self, key: str, agent: Any) -> None:
        self._agents[key] = agent

    def get_agent(self, key: str) -> Any | None:
        return self._agents.get(key)

    def list_agents(self) -> list[tuple[str, str]]:
        """Return [(key, description), ...] for all registered agents.

        Used by the supervisor to build its routing context.
        """
        return [
            (key, getattr(agent, "description", key))
            for key, agent in self._agents.items()
        ]


def build_registry(mcp_server: Any, skills_dir: Path | None = None) -> AgentRegistry:
    """Construct and return a fully populated AgentRegistry.

    Construction order:
    1. Hardcoded tool agents (reminders). These are always registered first.
       Their SKILL.md is loaded for behavioural instructions if available.
    2. skills/ folder scan — MCP agents discovered and constructed.
       Tool-type entries in skills/ are skipped with a warning.
       Keys already in the registry (from step 1) are deduplicated:
         - construction is skipped (the hardcoded agent wins)
         - SKILL.md body IS still loaded as the agent's instructions

    Args:
        mcp_server: The running workspace-mcp MCPServerStdio instance.
        skills_dir: Path to the skills/ folder. Defaults to Path("skills").

    Returns:
        A populated AgentRegistry with all agents registered.
    """
    if skills_dir is None:
        skills_dir = Path("skills")

    registry = AgentRegistry()

    # ── Step 1: Hardcoded tool agents ────────────────────────────────────────
    # Reminders is a tool agent — its Python functions must be bound at
    # construction time. It is always registered here regardless of skills/.

    reminders_skill = _load_skill_instructions("reminders", skills_dir)
    reminders_agent = RemindersAgent(
        instructions=reminders_skill.instructions if reminders_skill else "",
        description=(
            reminders_skill.description
            if reminders_skill
            else "Stores and retrieves personal reminders."
        ),
    )
    registry.register("reminders", reminders_agent)
    logger.info("registry | tool agent registered (hardcoded): reminders")

    # ── Step 2: skills/ scan — MCP agents ────────────────────────────────────
    all_skills = scan_skills_dir(skills_dir)

    for key, skill in all_skills.items():
        # Skip tool-type entries — they must be hardcoded above.
        if skill.type == "tool":
            if registry.get_agent(key) is not None:
                # Already registered via hardcoded path — load instructions only.
                _inject_instructions(registry.get_agent(key), skill.instructions)
            else:
                logger.warning(
                    "registry | %s is type 'tool' in skills/ but not hardcoded — skipping", key
                )
            continue

        # Deduplication: if already registered (via hardcoded path), load
        # instructions but skip construction.
        if registry.get_agent(key) is not None:
            logger.info(
                "registry | %s already registered (hardcoded) — loading instructions only", key
            )
            _inject_instructions(registry.get_agent(key), skill.instructions)
            continue

        # Construct MCP agent from skill metadata.
        agent = _build_mcp_agent(key, skill, mcp_server)
        if agent is None:
            continue

        registry.register(key, agent)
        logger.info("registry | mcp agent registered (skills scan): %s", key)

    total = len(registry._agents)
    logger.info("registry | build complete — %d agents registered", total)
    return registry


def _load_skill_instructions(key: str, skills_dir: Path) -> SkillMeta | None:
    """Load a SKILL.md for a hardcoded agent. Returns None if not found."""
    from core.skill_loader import load_skill
    path = skills_dir / key / "SKILL.md"
    if not path.exists():
        logger.warning(
            "registry | skills/%s/SKILL.md not found — agent will have no instructions", key
        )
        return None
    return load_skill(path)


def _inject_instructions(agent: Any, instructions: str) -> None:
    """Set or update an agent's instruction text after construction."""
    if hasattr(agent, "instructions"):
        agent.instructions = instructions


def _build_mcp_agent(key: str, skill: SkillMeta, mcp_server: Any) -> Any | None:
    """Construct a SpecialistAgent subclass for the given MCP skill.

    Maps well-known keys to their Python classes. Returns None and logs a
    warning for unknown keys — this is expected as new agents are added.

    In a future iteration this mapping could be eliminated by making all MCP
    agents use a single generic SpecialistAgent class parameterised by skill.
    That refactor belongs in Stage 3b or later, not here.
    """
    _MCP_AGENT_CLASSES = {
        "tasks": TasksAgent,
        "calendar": CalendarAgent,
        "email": EmailAgent,
    }

    cls = _MCP_AGENT_CLASSES.get(key)
    if cls is None:
        # Unknown key — construct a generic MCP agent.
        # This is the path exercised when a new skills/new_agent/SKILL.md is
        # dropped in without a corresponding Python class.
        from agents.specialist import SpecialistAgent  # generic base
        logger.info(
            "registry | %s: no dedicated class found — using generic SpecialistAgent", key
        )
        return SpecialistAgent(
            key=key,
            name=skill.name,
            description=skill.description,
            instructions=skill.instructions,
            mcp_server=mcp_server,
        )

    return cls(
        instructions=skill.instructions,
        description=skill.description,
        mcp_server=mcp_server,
    )
```

**Why a dict mapping for MCP agent classes?** The three existing MCP agents
(`tasks`, `calendar`, `email`) have dedicated Python classes from Stage 1d/2.
Those classes have specialised methods — field validation, error handling — that
a generic base class does not have. Preserving them avoids a large refactor.
New unknown agents fall back to the generic `SpecialistAgent` base, which is
sufficient for drop-in discovery.

**Why is `list_agents()` the supervisor interface and not `_agents` directly?**
The supervisor must never access `_agents` directly — encapsulation ensures the
registry can change its internal storage without breaking the supervisor. The
returned list of `(key, description)` tuples is the minimum the supervisor needs
to build its routing prompt.

---

## 9. `agents/reminders.py` — Full Implementation

The reminder agent is a tool agent. It manages a `reminders` table in the
existing SQLite database. It has no connection to `workspace-mcp`. It is entirely
self-contained — the only external dependency is `aiosqlite`, already present.

### 9.1 SQLite Schema

The `reminders` table is created in the same database initialisation path as
`agent_turns`. Both tables live in the same SQLite file at `SQLITE_PATH`.

The schema is created in `memory/sqlite_store.py` `initialise()`, alongside the
existing `agent_turns` DDL:

```python
# In memory/sqlite_store.py, inside initialise(), add after agent_turns DDL:

await db.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        text       TEXT    NOT NULL,
        remind_at  TEXT    NOT NULL,   -- ISO 8601 UTC string
        created_at TEXT    NOT NULL,   -- ISO 8601 UTC string
        fired      INTEGER NOT NULL DEFAULT 0
    )
""")
await db.commit()
```

**Why `fired INTEGER DEFAULT 0` now?** Stage 4 introduces an APScheduler that
marks reminders as fired when it sends the Telegram message. Adding the column
now avoids a schema migration in Stage 4. The column is set to 0 for all
Stage 3a operations.

**Why store `remind_at` as TEXT?** SQLite has no native datetime type. Storing
as ISO 8601 UTC string (`2025-06-15T14:00:00+00:00`) allows correct sorting with
plain string comparison and is unambiguous across timezones. The Python layer
handles conversion.

### 9.2 Pydantic Schema

```python
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


class Reminder(BaseModel):
    id: int
    text: str
    remind_at: datetime
    created_at: datetime
    fired: bool
```

### 9.3 Tool Functions

These are the three functions the agent uses as tools. They are async because
`aiosqlite` operations are coroutines. Each operates on the database at
`SQLITE_PATH` in `.env`.

```python
import os
from datetime import datetime, timezone

import aiosqlite

_DB_PATH = os.getenv("SQLITE_PATH", "data/assistant.db")


async def create_reminder(text: str, remind_at: datetime) -> Reminder:
    """Store a new reminder. Returns the created record.

    Args:
        text: The reminder text, e.g. "Call David".
        remind_at: The datetime to fire the reminder. If naive (no tzinfo),
                   UTC is assumed.

    Returns:
        The created Reminder with its assigned id.
    """
    if remind_at.tzinfo is None:
        remind_at = remind_at.replace(tzinfo=timezone.utc)

    now = datetime.now(tz=timezone.utc)

    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            """
            INSERT INTO reminders (text, remind_at, created_at, fired)
            VALUES (?, ?, ?, 0)
            """,
            (text, remind_at.isoformat(), now.isoformat()),
        )
        await db.commit()
        row_id = cursor.lastrowid

    return Reminder(
        id=row_id,
        text=text,
        remind_at=remind_at,
        created_at=now,
        fired=False,
    )


async def list_reminders(include_past: bool = False) -> list[Reminder]:
    """Return reminders from the database.

    Args:
        include_past: If False (default), returns only reminders with
                      remind_at in the future and fired=0.
                      If True, returns all reminders regardless of time or
                      fired status.

    Returns:
        List of Reminder objects, ordered by remind_at ascending.
    """
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        if include_past:
            cursor = await db.execute(
                "SELECT id, text, remind_at, created_at, fired "
                "FROM reminders ORDER BY remind_at ASC"
            )
        else:
            cursor = await db.execute(
                "SELECT id, text, remind_at, created_at, fired "
                "FROM reminders "
                "WHERE remind_at >= ? AND fired = 0 "
                "ORDER BY remind_at ASC",
                (now_iso,),
            )

        rows = await cursor.fetchall()

    return [
        Reminder(
            id=row["id"],
            text=row["text"],
            remind_at=datetime.fromisoformat(row["remind_at"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            fired=bool(row["fired"]),
        )
        for row in rows
    ]


async def delete_reminder(reminder_id: int) -> bool:
    """Delete a reminder by ID.

    Args:
        reminder_id: The integer ID of the reminder to delete.

    Returns:
        True if the reminder was found and deleted.
        False if no reminder with that ID exists.
    """
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM reminders WHERE id = ?", (reminder_id,)
        )
        await db.commit()
        deleted = cursor.rowcount > 0

    return deleted
```

### 9.4 The RemindersAgent Class

`RemindersAgent` is a `SpecialistAgent` subclass. It wires the three tool
functions above into the agent's tool set and builds its system prompt from the
`SKILL.md` body it receives at construction.

```python
from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import Agent

from core.deps import AgentDeps
from schemas.agent_response import AgentResponse

logger = logging.getLogger("reminders_agent")


class RemindersAgent:
    """Tool agent for reminder creation and retrieval.

    Unlike MCP agents, this agent does not connect to workspace-mcp.
    Its tools are Python functions that operate on the local SQLite database.
    """

    def __init__(self, instructions: str, description: str) -> None:
        self.description = description
        self.instructions = instructions
        self._agent = self._build_agent()

    def _build_system_prompt(self) -> str:
        base = (
            "You are a reminder assistant. You help the user store, list, and "
            "delete personal reminders.\n\n"
        )
        if self.instructions:
            base += self.instructions
        return base

    def _build_agent(self) -> Agent:
        import os
        model = os.getenv("SPECIALIST_MODEL", "openrouter/mistralai/ministral-8b-2512")

        agent = Agent(
            model=model,
            system_prompt=self._build_system_prompt(),
            result_type=AgentResponse,
        )

        # Register the three tool functions directly on the agent.
        # pydantic-ai's @agent.tool decorator can be applied after construction
        # using the functional registration API.
        agent.tool(create_reminder)
        agent.tool(list_reminders)
        agent.tool(delete_reminder)

        return agent

    async def run(self, user_input: str, deps: AgentDeps) -> AgentResponse:
        """Process a reminder-related request.

        Args:
            user_input: The user's message text.
            deps: AgentDeps carrying user identity. Not used for tool calls
                  but passed for logging consistency.

        Returns:
            AgentResponse with the agent's reply.
        """
        logger.info("reminders_agent | run | input=%r", user_input)
        result = await self._agent.run(user_input)
        logger.info("reminders_agent | run | output=%r", result.data.message)
        return result.data
```

**Why `agent.tool(create_reminder)` instead of `@agent.tool`?** The `@agent.tool`
decorator is applied at class definition time — before the `Agent` instance exists.
Since the `Agent` is constructed inside `_build_agent()`, the tools must be
registered after construction using the functional API (`agent.tool(fn)`).
`pydantic-ai` supports both forms identically — the decorator form is syntactic
sugar for the functional form.

**Why does `RemindersAgent` not inherit from `SpecialistAgent`?** The existing
`SpecialistAgent` base class from Stage 1d/2 is designed around MCP — its
constructor accepts an `mcp_server` argument and its system prompt injection is
tailored for MCP tool routing. Inheriting from it to then ignore the MCP wiring
would be misleading. `RemindersAgent` is a peer class, not a subclass. Both are
registered in the registry identically — the registry doesn't care about
inheritance, only about the `.run(user_input, deps)` interface.

---

## 10. Updated `gateway/app.py` — Lifespan Changes

Only the lifespan handler changes. The webhook handler, health endpoint,
`_agent_lock`, and `BackgroundTasks` pattern are unchanged from Stage 2.

The full updated lifespan:

```python
from __future__ import annotations

import asyncio
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request

from agents.supervisor import SupervisorAgent
from core.deps import AgentDeps
from core.logger import logger
from core.registry import build_registry
from gateway.telegram_client import send_message
from mcps.mcp_pool import start_pool_server, stop_pool_server
from memory.sqlite_store import SQLiteStore
from schemas.turn_record import TurnRecord

# ── environment ───────────────────────────────────────────────────────────────

_WEBHOOK_SECRET  = os.getenv("WEBHOOK_SECRET", "")
_ALLOWED_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "0"))
_USER_ID         = os.getenv("USER_ID", "local_user")
_USER_EMAIL      = os.getenv("USER_GOOGLE_EMAIL", "")
_LLM_MODEL       = os.getenv("LLM_MODEL", "")
_BOT_TOKEN       = os.getenv("TELEGRAM_BOT_TOKEN", "")

# ── application state ─────────────────────────────────────────────────────────

_supervisor: SupervisorAgent
_store: SQLiteStore
_agent_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic.

    Startup order (each step depends on the previous):
      1. Validate environment
      2. Clear pending Telegram updates
      3. Initialise SQLite store (creates tables including reminders)
      4. Start workspace-mcp persistent subprocess        ← NEW Stage 3a
      5. Build registry (tool agents + MCP agents scan)  ← NEW Stage 3a
      6. Construct SupervisorAgent with completed registry
    """
    global _supervisor, _store

    # 1. Validate environment
    if not _USER_EMAIL:
        raise RuntimeError("USER_GOOGLE_EMAIL is not set")
    if not _WEBHOOK_SECRET:
        raise RuntimeError("WEBHOOK_SECRET is not set")
    if not _ALLOWED_CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is not set")
    if not _BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")

    # 2. Clear pending Telegram updates (prevents message flood on restart).
    # This is done before the supervisor is constructed — if Telegram floods
    # messages the moment the webhook goes live, the registry may not be ready.
    async with httpx.AsyncClient() as client:
        await client.post(
            f"https://api.telegram.org/bot{_BOT_TOKEN}/deleteWebhook",
            params={"drop_pending_updates": "true"},
        )
    logger.info("gateway | pending Telegram updates cleared")

    # 3. Initialise SQLite store.
    # Creates agent_turns and reminders tables if they do not exist.
    _store = SQLiteStore()
    await _store.initialise()
    logger.info("gateway | SQLite store initialised")

    # 4. Start workspace-mcp persistent subprocess.
    # Must complete before the registry is built — MCP agents hold a reference
    # to this server and cannot be constructed without it.
    mcp_server = await start_pool_server("workspace-mcp")

    # 5. Build registry.
    # Hardcoded tool agents first, then MCP agents from skills/ scan.
    registry = build_registry(mcp_server=mcp_server)

    # 6. Construct SupervisorAgent with completed registry.
    _supervisor = SupervisorAgent(registry=registry)

    logger.info(
        "gateway | started | user=%s | email=%s | allowed_chat_id=%d",
        _USER_ID, _USER_EMAIL, _ALLOWED_CHAT_ID,
    )
    yield

    # Shutdown — tear down in reverse order.
    await stop_pool_server()
    logger.info("gateway | shutdown")


app = FastAPI(lifespan=lifespan)


# ── health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


# ── webhook ───────────────────────────────────────────────────────────────────
# The webhook handler is UNCHANGED from Stage 2.
# It calls _supervisor.run(text, deps) identically.
# All changes are in lifespan above.

@app.post("/webhook/{secret}")
async def webhook(secret: str, request: Request, background_tasks: BackgroundTasks) -> dict:
    if secret != _WEBHOOK_SECRET:
        logger.warning("webhook | invalid secret | received=%r", secret)
        raise HTTPException(status_code=403, detail="Forbidden")

    update = await request.json()
    logger.debug("webhook | update=%r", update)

    message = update.get("message")
    if not message:
        return {"ok": True}

    chat_id: int = message.get("chat", {}).get("id", 0)
    text: str = message.get("text", "").strip()

    if chat_id != _ALLOWED_CHAT_ID:
        logger.warning("webhook | unauthorised chat_id=%d | ignoring", chat_id)
        return {"ok": True}

    if not text:
        return {"ok": True}
    if text.startswith("/"):
        if text == "/start":
            await send_message(chat_id, "Assistant ready. Send me a message.")
        return {"ok": True}

    logger.info("webhook | chat_id=%d | text=%r", chat_id, text)

    deps = AgentDeps(user_id=_USER_ID, user_email=_USER_EMAIL)

    background_tasks.add_task(_process_message, chat_id, text, deps)
    return {"ok": True}


async def _process_message(chat_id: int, text: str, deps: AgentDeps) -> None:
    """Run the agent loop and send the reply. Serialised by _agent_lock."""
    async with _agent_lock:
        try:
            response = await _supervisor.run(text, deps)
        except Exception:
            logger.exception("webhook | agent loop failed | chat_id=%d", chat_id)
            await send_message(chat_id, "Something went wrong. Please try again.")
            return

        await send_message(chat_id, response.message)

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
```

**What changed from Stage 2:** Only the lifespan handler. Steps 4 and 5 are new.
The webhook handler, `_process_message`, health endpoint, and lock are unchanged.
The supervisor still receives a `registry` argument — it had this in Stage 2,
the registry was just constructed differently (hardcoded inline). Now the
registry is passed in from the lifespan.

---

## 11. `memory/sqlite_store.py` — One Addition

The only change to `sqlite_store.py` is adding the `reminders` table DDL inside
`initialise()`. Everything else is unchanged.

Locate the `initialise()` method and add the block below immediately after the
`agent_turns` `CREATE TABLE` statement:

```python
# In memory/sqlite_store.py → initialise() method, add after agent_turns DDL:

await db.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        text       TEXT    NOT NULL,
        remind_at  TEXT    NOT NULL,
        created_at TEXT    NOT NULL,
        fired      INTEGER NOT NULL DEFAULT 0
    )
""")
```

No other changes to this file.

---

## 12. The Four SKILL.md Files

Create these four files exactly. They govern agent behaviour — edit them freely
as the assistant matures. No code change required.

### `skills/tasks/SKILL.md`

```markdown
---
key: tasks
name: Tasks Agent
type: mcp
mcp_server: workspace-mcp
description: Creates and manages tasks in Google Tasks from natural language.
---

## Behaviour

- Always confirm the task title before creating.
- If the user specifies a due date, include it. If not, create the task without one — do not ask for a date unless the user seems to expect one.
- After creating a task, confirm with: title and due date (if set).
- When listing tasks, show title and due date. If no due date, omit it.

## Edge Cases

- Vague tasks ("do that thing") — ask for clarification before creating.
- Past due dates — create without comment unless the user seems to have made an error.
- If the user says "add to my list", treat it as a task creation request.
```

### `skills/calendar/SKILL.md`

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
- After creating an event, confirm with: date, time, title, and duration.

## Edge Cases

- Ambiguous dates ("next Friday", "end of month") — restate your interpretation before acting: "I'll set that for Friday 6 June — confirm?"
- Overlapping events — warn the user if a conflict is detected.
- Past dates — confirm explicitly before creating.
- "Schedule a meeting" without attendees — create for the user only, no invite sent.
```

### `skills/email/SKILL.md`

```markdown
---
key: email
name: Email Agent
type: mcp
mcp_server: workspace-mcp
description: Sends emails via Gmail on the user's behalf.
---

## Behaviour

- Always confirm recipient, subject, and a summary of the body before sending.
- Never send without explicit confirmation from the user.
- After sending, confirm: recipient, subject, and time sent.

## Edge Cases

- Missing recipient — ask before doing anything else.
- Missing subject — ask, or offer to generate one from the body.
- Long bodies — summarise for confirmation ("I'll send this: [first 100 chars]...").
- If the user provides a name instead of an email address — in Stage 3a, ask for the full address. Stage 3b will handle name lookups via user.md.
```

### `skills/reminders/SKILL.md`

```markdown
---
key: reminders
name: Reminder Agent
type: tool
description: Stores and retrieves personal reminders with a scheduled date and time.
---

## Behaviour

- When storing a reminder, always confirm the exact text and the scheduled time.
- If the user does not specify a time, ask before creating.
- When listing reminders, show each one with its ID, text, and scheduled time.
- When deleting, confirm the ID and text of what was deleted.
- If the reminders list is empty, say: "You have no upcoming reminders."

## Scope in Stage 3a

This agent stores and retrieves only. When a reminder is created, tell the user:
"Reminder set for [time]. Note: I won't send you a proactive message yet — that's coming soon."
Stage 4 adds the scheduler that fires reminders automatically.

## Edge Cases

- Ambiguous times ("tomorrow morning") — ask for the specific time.
- "Delete reminder 1" where ID 1 does not exist — say so clearly.
- "What reminders do I have?" with no upcoming reminders — say so clearly.
```

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

`pyyaml` is the only new dependency. It parses YAML frontmatter in `SKILL.md`
files. It is a pure Python package with no binary extensions — no platform issues.

After adding it, regenerate your pinned `requirements.txt`:

```powershell
pip install pyyaml
pip freeze > requirements.txt
```

Apply the same `pywin32` platform guard from Stage 2 if it reappears:
```
pywin32==311; sys_platform == 'win32'
```

---

## 14. How the Existing MCP Agents Change

`agents/tasks.py`, `agents/calendar.py`, and `agents/email.py` are not
rewritten. Their internal tool routing, field validation, and MCP wiring are
unchanged. Only two things change:

### 14.1 Constructor signature

Each class must accept `instructions`, `description`, and `mcp_server` keyword
arguments, because the registry now passes these at construction:

```python
# Before (Stage 2 — hardcoded)
class TasksAgent(SpecialistAgent):
    def __init__(self) -> None:
        super().__init__(
            mcp_server=MCPServerStdio("uvx", args=["workspace-mcp"]),
        )

# After (Stage 3a — accepts arguments from registry)
class TasksAgent(SpecialistAgent):
    def __init__(
        self,
        instructions: str,
        description: str,
        mcp_server: Any,
    ) -> None:
        super().__init__(
            mcp_server=mcp_server,
            instructions=instructions,
            description=description,
        )
```

The same pattern applies to `CalendarAgent` and `EmailAgent`. The MCP server
is now passed in from the pool rather than constructed inline.

### 14.2 System prompt injection

Each agent's `_build_system_prompt()` gains the injected `instructions` from
`SKILL.md`. If `instructions` is an empty string (the skill file was missing),
the agent falls back to its hardcoded strings exactly as in Stage 2 — no
behaviour change.

```python
# In SpecialistAgent base class or each subclass _build_system_prompt():

def _build_system_prompt(self) -> str:
    base = self._hardcoded_base_prompt()   # unchanged from Stage 2
    if self.instructions:
        return base + "\n\n" + self.instructions
    return base
```

No other changes to these files.

---

## 15. Project Structure After Stage 3a

```
project/
├── skills/
│   ├── tasks/
│   │   └── SKILL.md                 # NEW
│   ├── calendar/
│   │   └── SKILL.md                 # NEW
│   ├── email/
│   │   └── SKILL.md                 # NEW
│   └── reminders/
│       └── SKILL.md                 # NEW
│
├── agents/
│   ├── reminders.py                 # NEW
│   ├── tasks.py                     # UPDATED — constructor + prompt injection
│   ├── calendar.py                  # UPDATED — constructor + prompt injection
│   └── email.py                     # UPDATED — constructor + prompt injection
│
├── core/
│   ├── registry.py                  # REWRITTEN — hybrid + skills scan
│   └── skill_loader.py              # NEW
│
├── mcps/
│   └── mcp_pool.py                  # UPDATED — start/stop + singleton
│
├── memory/
│   └── sqlite_store.py              # UPDATED — reminders table DDL added
│
├── gateway/
│   └── app.py                       # UPDATED — lifespan steps 4+5 added
│
└── requirements.txt                 # UPDATED — pyyaml added
```

Unchanged: `main.py`, `agents/supervisor.py`, `core/deps.py`, `core/logger.py`,
`schemas/`, `gateway/telegram_client.py`, `Dockerfile`, `docker-compose.yml`,
`.env`.

---

## 16. Implementation Phases

Each phase must be fully validated before moving to the next. Do not skip ahead.

### Phase 1 — Persistent MCP server

**What to do:**

1. Open `mcps/mcp_pool.py`. Replace the existing content with the updated version
   from Section 7. The key additions are: the `_server` module-level global,
   `start_pool_server()`, and `stop_pool_server()`. Remove any per-request
   subprocess spawning that existed in the Stage 2 version.

2. Open `gateway/app.py`. In the lifespan handler, add step 4 (start MCP server)
   before step 5 (build registry / construct supervisor). Pass the returned
   `mcp_server` reference into `build_registry()`. Add `stop_pool_server()` in
   the shutdown block.

   At this point `build_registry()` does not yet exist — temporarily keep the
   Stage 2 inline supervisor construction. The purpose of Phase 1 is to validate
   that the persistent server starts and that the cold start is gone.

3. Update each MCP agent's constructor to accept `mcp_server` as an argument
   instead of constructing `MCPServerStdio` inline. Pass the pool server in from
   lifespan when constructing agents.

**Pass/fail:**

```powershell
uvicorn gateway.app:app --reload
```

Expected log line:
```
mcp_pool | workspace-mcp started
```

Send a task creation message immediately after a fresh start. Time the response.
Expected: under 3 seconds (was 10–20 seconds in Stage 2).

Full Telegram flow must work identically to Stage 2. If anything breaks,
roll back `mcp_pool.py` and `app.py` before proceeding.

---

### Phase 2 — Skill files and loader

**What to do:**

1. Create the `skills/` directory at the project root.

2. Create the four `SKILL.md` files from Section 12 exactly:
   - `skills/tasks/SKILL.md`
   - `skills/calendar/SKILL.md`
   - `skills/email/SKILL.md`
   - `skills/reminders/SKILL.md`

3. Create `core/skill_loader.py` from Section 6 exactly.

4. Write unit tests in `tests/test_skill_loader.py`:

```python
# tests/test_skill_loader.py

import pytest
from pathlib import Path
from core.skill_loader import load_skill, scan_skills_dir, SkillMeta

# ── load_skill tests ──────────────────────────────────────────────────────────

def test_load_skill_valid_mcp(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text(
        "---\nkey: tasks\nname: Tasks Agent\ntype: mcp\n"
        "mcp_server: workspace-mcp\ndescription: Manages tasks.\n---\n\n## Instructions\nDo things.\n"
    )
    skill = load_skill(f)
    assert skill is not None
    assert skill.key == "tasks"
    assert skill.type == "mcp"
    assert skill.mcp_server == "workspace-mcp"
    assert "Do things." in skill.instructions


def test_load_skill_valid_tool(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text(
        "---\nkey: reminders\nname: Reminder Agent\ntype: tool\n"
        "description: Stores reminders.\n---\n\n## Instructions\nStore carefully.\n"
    )
    skill = load_skill(f)
    assert skill is not None
    assert skill.type == "tool"
    assert skill.mcp_server is None


def test_load_skill_missing_frontmatter(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("No frontmatter here at all.")
    skill = load_skill(f)
    assert skill is None


def test_load_skill_missing_required_field(tmp_path):
    f = tmp_path / "SKILL.md"
    # Missing 'description'
    f.write_text("---\nkey: foo\nname: Foo\ntype: mcp\nmcp_server: x\n---\n\nbody\n")
    skill = load_skill(f)
    assert skill is None


def test_load_skill_mcp_without_mcp_server(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("---\nkey: foo\nname: Foo\ntype: mcp\ndescription: A thing.\n---\n\nbody\n")
    skill = load_skill(f)
    assert skill is None


def test_load_skill_malformed_yaml(tmp_path):
    f = tmp_path / "SKILL.md"
    f.write_text("---\nkey: [unclosed\n---\nbody\n")
    skill = load_skill(f)
    assert skill is None


# ── scan_skills_dir tests ─────────────────────────────────────────────────────

def test_scan_skills_dir_returns_mcp_agents(tmp_path):
    for key, server in [("tasks", "workspace-mcp"), ("calendar", "workspace-mcp")]:
        d = tmp_path / key
        d.mkdir()
        (d / "SKILL.md").write_text(
            f"---\nkey: {key}\nname: {key.title()}\ntype: mcp\n"
            f"mcp_server: {server}\ndescription: Does {key}.\n---\n\ninstructions\n"
        )

    result = scan_skills_dir(tmp_path)
    assert set(result.keys()) == {"tasks", "calendar"}


def test_scan_skills_dir_skips_missing_skill_md(tmp_path):
    d = tmp_path / "empty_agent"
    d.mkdir()
    # No SKILL.md inside
    result = scan_skills_dir(tmp_path)
    assert result == {}


def test_scan_skills_dir_nonexistent_dir(tmp_path):
    result = scan_skills_dir(tmp_path / "does_not_exist")
    assert result == {}
```

Run tests:
```powershell
pytest tests/test_skill_loader.py -v
```

Expected: all tests pass.

**Pass/fail:** All unit tests pass. The four `SKILL.md` files are readable by
`scan_skills_dir`. Confirm manually:

```python
from pathlib import Path
from core.skill_loader import scan_skills_dir
skills = scan_skills_dir(Path("skills"))
print(list(skills.keys()))
# Expected: ['calendar', 'email', 'reminders', 'tasks']  (alphabetical)
```

---

### Phase 3 — Reminder agent

**What to do:**

1. Add the `reminders` table DDL to `memory/sqlite_store.py` `initialise()` as
   shown in Section 11.

2. Create `agents/reminders.py` from Section 9 exactly.

3. Test the reminder agent in isolation using `python main.py`. The supervisor
   must route reminder-related messages to `RemindersAgent`. For this phase, wire
   `RemindersAgent` into the registry temporarily via the same inline path used
   for other agents in Stage 2 — the hybrid registry comes in Phase 4.

**Pass/fail:**

```powershell
python main.py
```

| Input | Expected output |
|---|---|
| `Remind me to call David tomorrow at 3pm` | "Reminder set for [date] at 3:00 PM. Note: I won't send a proactive message yet — that's coming soon." |
| `What reminders do I have?` | Lists the reminder with ID, text, and time |
| `Delete reminder 1` | "Reminder deleted: Call David" |
| `What reminders do I have?` | "You have no upcoming reminders." |

Verify the SQLite table directly:

```powershell
# After creating a reminder:
sqlite3 data/assistant.db "SELECT * FROM reminders;"
# Expected: one row with id=1, text, remind_at, fired=0

# After deleting:
sqlite3 data/assistant.db "SELECT * FROM reminders;"
# Expected: empty
```

---

### Phase 4 — Hybrid registry

**What to do:**

1. Rewrite `core/registry.py` from Section 8 exactly.

2. Update `gateway/app.py` lifespan to call `build_registry(mcp_server)` as
   shown in Section 10 (replacing any inline agent construction from Phase 1).

3. Update each MCP agent's constructor to accept `instructions`, `description`,
   and `mcp_server` as arguments as shown in Section 14.

4. Test new-agent discovery: create a dummy skill file, restart, confirm it is
   discovered. Remove it, confirm registry returns to 4 agents.

```powershell
# Create dummy skill
mkdir skills\test_agent
@"
---
key: test_agent
name: Test Agent
type: mcp
mcp_server: workspace-mcp
description: A temporary test agent.
---

## Instructions
Do nothing. This agent is for testing discovery only.
"@ | Out-File skills\test_agent\SKILL.md -Encoding utf8

uvicorn gateway.app:app --reload
```

Expected log:
```
registry | mcp agent registered (skills scan): test_agent
registry | build complete — 5 agents registered
```

Remove the folder, restart:
```powershell
Remove-Item -Recurse -Force skills\test_agent
# Restart uvicorn
```

Expected:
```
registry | build complete — 4 agents registered
```

**Pass/fail:** Registry builds at startup with all four agents. Startup logs show
correct sequence (MCP server → hardcoded tool agents → MCP agents from scan →
supervisor). Dummy agent discovery works. All Stage 2 Telegram flow unchanged.

---

### Phase 5 — Full integration test

Restart the app and confirm the full startup log sequence:

```
mcp_pool | workspace-mcp started
skill_loader | loaded skills/tasks/SKILL.md
skill_loader | loaded skills/calendar/SKILL.md
skill_loader | loaded skills/email/SKILL.md
skill_loader | loaded skills/reminders/SKILL.md
registry | tool agent registered (hardcoded): reminders
registry | mcp agent registered (skills scan): tasks
registry | mcp agent registered (skills scan): calendar
registry | mcp agent registered (skills scan): email
registry | build complete — 4 agents registered
gateway | started | user=local_user | email=...
```

Run the full Telegram smoke test from Section 17.

Run `python main.py` and confirm the CLI loop still works for all four agent types.

---

## 17. Validation Steps

### Step 1 — Confirm persistent MCP server starts

```powershell
uvicorn gateway.app:app --reload
```

Expected log line (appears before `gateway | started`):
```
mcp_pool | workspace-mcp started
```

If this line does not appear, the lifespan order is wrong or `start_pool_server`
raised an exception — check for a traceback.

### Step 2 — Confirm cold start is gone

Send a message immediately after a fresh app start (Ctrl+C then relaunch).
Expected response time: under 3 seconds for the first tool call.

Compare to Stage 2 where the first tool call after a fresh start took 10–20
seconds. If still slow, the persistent server is not being used — check that
agent constructors receive `mcp_server` from the pool, not construct their own.

### Step 3 — Confirm skill files load

Expected log lines at startup (order may vary within the scan):
```
skill_loader | loaded skills/tasks/SKILL.md
skill_loader | loaded skills/calendar/SKILL.md
skill_loader | loaded skills/email/SKILL.md
skill_loader | loaded skills/reminders/SKILL.md
```

If a file is missing, a `skill_loader | cannot read ...` warning appears instead.
The app does not crash — the agent runs without custom instructions.

### Step 4 — Confirm registry build sequence

Expected log lines in this exact order:
```
registry | tool agent registered (hardcoded): reminders
registry | mcp agent registered (skills scan): tasks
registry | mcp agent registered (skills scan): calendar
registry | mcp agent registered (skills scan): email
registry | build complete — 4 agents registered
```

If `reminders` does not appear first, the hardcoded path is running after the
scan — fix the construction order in `build_registry()`.

### Step 5 — Confirm new MCP agent discovery

Follow the dummy skill procedure from Phase 4 above.

### Step 6 — Reminder agent smoke test (CLI)

```powershell
python main.py
```

| Input | Expected |
|---|---|
| `Remind me to call David tomorrow at 3pm` | Confirmation with date and time, note about Stage 4 proactive messages |
| `What reminders do I have?` | Lists reminder with ID, text, and scheduled time |
| `Delete reminder 1` | Confirmation of deletion |
| `What reminders do I have?` | "You have no upcoming reminders." |

Confirm SQLite state after each operation:
```powershell
sqlite3 data/assistant.db "SELECT id, text, remind_at, fired FROM reminders;"
```

### Step 7 — Full Telegram smoke test

| Message | Expected |
|---|---|
| `What can you help me with?` | Reply in Telegram, no tool call |
| `Add a task called Review report due this Friday` | Task in Google Tasks, confirmation |
| `Schedule a meeting called Stage 3a review for next Monday at 2pm` | Calendar event created, confirmation |
| `Send an email to your@gmail.com subject Stage 3a test body Architecture complete` | Email delivered, confirmation |
| `Remind me to review the budget next Monday at 9am` | Reminder stored, confirmation with time |
| `What reminders do I have?` | Lists the reminder |
| `Delete reminder 1` | Confirmation of deletion |
| `/start` | `Assistant ready. Send me a message.` |

### Step 8 — Docker smoke test

```powershell
docker compose up -d --build
curl http://localhost:10000/health
```

Expected: `{"status":"ok"}`

```powershell
docker compose logs --tail=30
```

Expected: same startup log sequence as Step 4 above, now from inside the container.

Run all Telegram smoke tests from Step 7 through Docker. Behaviour must be
identical to local uvicorn.

---

## 18. Troubleshooting

**`mcp_pool.get_pool_server()` raises RuntimeError at startup**

The registry is being constructed before `start_pool_server()` completes. Check
the lifespan handler — `start_pool_server()` must be called and awaited before
`build_registry()` is called.

**`workspace-mcp` fails to start in lifespan**

Credentials must be available at startup, not at first tool call. In Stage 2,
missing credentials only surfaced on the first tool call. In Stage 3a they cause
a startup failure. Confirm the credential volume mount is present (Docker) or
the credential file exists on disk (local). Check logs for an auth error traceback.

**Skill file not loaded**

Confirm the file is named exactly `SKILL.md` (case-sensitive on Linux — the
Docker container runs Linux). Confirm YAML frontmatter is delimited with `---`
on its own line at both the top and after the last field. Any YAML parse error
causes the file to be skipped with a warning — check logs for
`skill_loader | ... YAML parse error`.

**MCP agent in `skills/` not discovered**

Confirm `type: mcp` is in the frontmatter. `type: tool` entries are skipped with
a warning. Confirm the `key` does not collide with a hardcoded agent — check logs
for `already registered (hardcoded)`.

**Reminder agent not found by supervisor**

The reminder agent does not come from `skills/` scan — it is constructed in the
hardcoded path in `build_registry()`. If missing, confirm `RemindersAgent` is
imported and constructed before the scan loop in `build_registry()`. Check logs
for `tool agent registered (hardcoded): reminders` — if absent, the hardcoded
block did not run.

**Stage 2 Telegram flow broken after registry rewrite**

The registry's public interface (`get_agent`, `list_agents`) must not change.
Confirm all four agents are registered under their original keys: `tasks`,
`calendar`, `email`, `reminders`. The supervisor calls the registry identically
to Stage 2 — if the keys changed, routing breaks.

**SQLite schema error on reminders table**

Confirm the `reminders` DDL was added to `initialise()` in `sqlite_store.py`.
Delete `data/assistant.db` and restart — `initialise()` will recreate all tables
from scratch. Do not delete the database if it contains real data you want to
keep; run the DDL manually instead:
```powershell
sqlite3 data/assistant.db "CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, remind_at TEXT NOT NULL, created_at TEXT NOT NULL, fired INTEGER NOT NULL DEFAULT 0);"
```

**MCP agents still constructing their own `MCPServerStdio` subprocess**

Check that each agent's constructor no longer contains `MCPServerStdio("uvx", args=["workspace-mcp"])`. This should now come from the `mcp_server` argument passed in from `build_registry()`. If an agent constructs its own subprocess, cold starts reappear and two competing subprocess connections cause failures.

---

## 19. How Stage 3b Builds on This

Stage 3a establishes how agents are built and discovered. The registry is
complete, the persistent MCP server is running, and skill instructions are loaded.
Nothing in Stage 3a changes in Stage 3b.

Stage 3b enriches those agents with knowledge of who they are and who they are
talking to. Two new markdown files are loaded at startup:

- `memory/agents/<key>.md` — each agent's persona: tone, style, boundaries. The
  calendar agent is formal and concise. The tasks agent is brief and direct.
- `memory/brain/user.md` — facts about you: timezone (MYT), preferred deadline
  day, contact name shortcuts, email preferences.

A new `memory/markdown_store.py` loader handles reading these files at startup.
Each agent's `_build_system_prompt()` gains a second injection point: the persona
and user context from `markdown_store` alongside the `SKILL.md` body.

The registry, skill loader, persistent MCP server, and reminder agent do not
change in Stage 3b. Stage 3b is one new loader and one new injection per agent.

---

## 20. Done When

- App starts and logs MCP server start, skill file loads, and registry build
  in the correct sequence shown in Section 16 Phase 5
- `workspace-mcp` cold start is eliminated — first tool call under 3 seconds
  on a fresh app start
- All four agents registered: `reminders` (hardcoded tool), `tasks`, `calendar`,
  `email` (discovered MCP)
- Each agent has a `SKILL.md` with behavioural instructions
- A new `SKILL.md` with `type: mcp` dropped into `skills/` is discovered and
  registered without any code change
- Reminder create, list, and delete work via both CLI and Telegram
- All Stage 2 smoke tests pass unchanged
- `python main.py` CLI loop still works for all four agent types
- `docker compose up -d --build` produces a working container with the same
  startup log sequence