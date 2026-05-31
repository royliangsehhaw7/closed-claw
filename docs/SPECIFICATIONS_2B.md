# Personal Telegram Assistant
## Specification — Stage 3a: Agent Architecture

> **Assumes:** Stage 2 complete and merged to `main` — Telegram messages arrive
> via webhook, the FastAPI gateway runs, the agent loop executes, replies are sent,
> every exchange written to SQLite `agent_turns`. `SupervisorAgent`,
> `SpecialistAgent` (tasks, calendar, email), and the Docker image are all stable.
> `python main.py` CLI loop still works.
>
> **Branch:** `stage/3a` branched from `main` after Stage 2 merge
>
> **Done when:** The registry builds itself at startup by scanning `skills/` for
> agent definitions. Each agent's identity, tool surface, and behavioural
> instructions come entirely from its `SKILL.md`. `SupervisorAgent` calls
> `load_registry_from_disk()` at construction time and delegates via
> `build_specialist()`. The full Telegram flow works identically to Stage 2 —
> no behaviour changes, only structural ones. The reminder agent creates, lists,
> and deletes reminders via both CLI and Telegram.

---

## 1. What Stage 3a Adds

Stage 2 delivered a working Telegram gateway. The agent loop is proven end-to-end.
The question for Stage 3a is not whether the system works — it does — but whether
it can grow without touching Python every time something needs to change.

Right now two things require a code edit, a commit, and a redeploy:

- **Adding a new MCP specialist** — hardcoded in `core/registry.py`
- **Changing how a specialist behaves** — strings embedded inside `_build_system_prompt()`

Stage 3a fixes both. It also introduces the first **tool agent** — the reminder
agent — which gives the assistant a genuinely useful new capability.

**What changes at the code level:**

| File | Change |
|---|---|
| `skills/tasks/SKILL.md` | NEW — tasks agent definition and behavioural instructions |
| `skills/calendar/SKILL.md` | NEW — calendar agent definition and behavioural instructions |
| `skills/email/SKILL.md` | NEW — email agent definition and behavioural instructions |
| `skills/reminders/SKILL.md` | NEW — reminders agent definition and behavioural instructions |
| `agents/reminders.py` | NEW — RemindersAgent, tool functions, SQLite schema |
| `core/registry.py` | REWRITTEN — pure data registry, disk scan, lazy specialist construction |
| `agents/supervisor.py` | UPDATED — calls `load_registry_from_disk()` at construction |
| `agents/specialist.py` | UPDATED — receives `AgentRegistration`, calls `get_pool_server()` |
| `mcps/mcp_pool.py` | UPDATED — lazy cache keyed by `(user_email, services)` |

**What does not change:**

`gateway/app.py` lifespan — no MCP subprocess management here. `AgentDeps`,
`SQLiteStore` (except reminders DDL addition), `TurnRecord`, `schemas/`,
`gateway/telegram_client.py` — none of these are touched.

---

## 2. Architecture

### The Key Insight

`MCPServerStdio` from pydantic-ai manages its own subprocess lifecycle when the
agent runs. There is no `.start()` method to call, no explicit lifecycle to manage.
`get_pool_server()` is a lazy cache — it constructs an `MCPServerStdio` instance
on first call for a given `(user_email, services)` combination and returns the same
instance on every subsequent call. pydantic-ai handles the rest.

This means:

- `gateway/app.py` lifespan has no MCP responsibilities — it only initialises
  SQLite and constructs `SupervisorAgent`
- No startup ordering constraints between MCP and registry
- No risk of subprocess race conditions

### How the Registry Works

The `AgentRegistry` is a singleton-style class instance. It manages the lifecycle of agent definitions internally. The SupervisorAgent owns an instance of the registry, which it populates at construction time. Rather than global access, components interact with the registry instance via defined methods.

`SupervisorAgent.__init__()` calls `load_registry_from_disk()` which clears and
repopulates `AGENT_REGISTRY` from disk. The registry is not passed around — it
is a module-level global accessed by name wherever needed.

`build_specialist(key, user_email)` instantiates a `SpecialistAgent` on demand
from the registry entry for that key. Called inside `delegate_to_specialists()`
at request time, not at startup.

### How a Request Flows

```
## 2. Request Flow & System Architecture

The following diagram illustrates the encapsulated lifecycle of a request. The SupervisorAgent acts as the orchestrator, owning an instance of the AgentRegistry, which functions as a factory to construct specialists on-demand with their specific identities.

+-------------------------------------------------------------+
| Telegram Message                                            |
+-------------------------------------------------------------+
              │
              ▼
+-------------------------------------------------------------+
| FastAPI Webhook Handler (Returns 200 immediately)           |
+-------------------------------------------------------------+
              │ (Background Task)
              ▼
+-------------------------------------------------------------+
| SupervisorAgent (Instance Lifecycle)                        |
|   ├── holds self._registry: AgentRegistry (Singleton Class) |
+-------------------------------------------------------------+
│    │
│    ├── [Orchestration] Decision: Direct Answer OR Delegate?
│    │
│    └── [Delegation] self._registry.build_specialist(key)
│              │
│              └── [Factory: AgentRegistry instance validates key]
│                   │
│                   └── [Identity Injection]:
│                        - Parses SKILL.md (YAML + Instructions)
│                        - Construct: SpecialistAgent(registration)
│                        - Injects identity into system prompt
│              │
│              ▼
│    +--------------------------------------------------------+
│    | SpecialistAgent (Operational Domain)                   |
│    +--------------------------------------------------------+
│                   │
│                   └── specialist.run(sub_task)
│                           │
│                           └── get_pool_server(services)
│                                   │
│                                   ▼
│                          pydantic-ai Agent.run()
│                                   │
│                                   └── Workspace MCP Tools
+-------------------------------------------------------------+
```

---

## 3. `SKILL.md` Format

Every agent has a `SKILL.md` file under `skills/<key>/SKILL.md`. The file has
two parts: a YAML frontmatter block and a markdown body.

### Frontmatter

```yaml
---
key: "tasks"
name: "tasks"
services: ["tasks"]
owns: "Google Tasks management"
description: "Handles creating, viewing, updating, and completing items in the user's Google Task lists."
---
```

| Field | Required | Type | Description |
|---|---|---|---|
| `key` | yes | string | Unique agent identifier. Used for registry lookup. Lowercase, no spaces. |
| `name` | yes | string | Human-readable display name. Used in logs. |
| `services` | yes | list[str] | MCP service names passed to `get_pool_server()`. Controls the tool surface exposed to this agent. Empty list for tool agents. |
| `owns` | yes | string | Domain description injected into `SpecialistAgent._build_system_prompt()`. Tells the LLM what it is responsible for. |
| `description` | yes | string | One-line summary injected into the supervisor's routing prompt so it knows which agent to call. |

### Markdown body

Everything after the closing `---` is the behavioural instructions body. This
is injected into the specialist's system prompt at construction time. Write it
as instructions to the agent — what to do, what to ask, how to confirm.

### Full example — `skills/tasks/SKILL.md`

```markdown
---
key: "tasks"
name: "tasks"
services: ["tasks"]
owns: "Google Tasks management"
description: "Handles creating, viewing, updating, and completing items in the user's Google Task lists."
---
You are a highly efficient specialist agent dedicated exclusively to Google Tasks management.

Your core responsibility is to inspect, create, modify, or complete tasks across the user's task lists.

Guidelines:
1. Extraction: Carefully extract the task title, due dates, notes, or list names from the incoming sub-task instruction.
2. Missing Information: If the instruction implies creating a task but lacks a definitive title or objective, do not guess. Flag the exact item required in your output structure.
3. Execution & Validation: Execute the appropriate tool call to satisfy the request. Confirm the action succeeded before preparing your response.
4. Output Reporting: Provide a concise summary of the action, log every concrete modification in the actions list, and note any unresolved details.
```

### Full example — `skills/reminders/SKILL.md`

```markdown
---
key: "reminders"
name: "reminders"
services: []
owns: "Personal reminder management"
description: "Stores and retrieves personal reminders with a date and time. Does not send proactive messages — that is Stage 4."
---
You are a reminder specialist. You store, list, and delete personal reminders.

Guidelines:
1. When storing a reminder, always confirm the exact text and the scheduled time before acting.
2. If the user does not specify a time, ask — never assume.
3. When listing reminders, show each one with its ID, text, and scheduled time.
4. When deleting, confirm the ID and text of what was deleted.
5. In Stage 3a this agent stores and retrieves only. It does not send proactive Telegram messages. Tell the user their reminder is saved and that proactive delivery is coming soon.

Edge Cases:
- Ambiguous times ("tomorrow morning") — ask for clarification.
- If the user asks to delete a reminder that does not exist, say so clearly.
- If the reminders list is empty, say "You have no upcoming reminders."
```

---

## 4. `core/registry.py` — Full Implementation

Pure data. No agent construction at scan time. No MCP references. No async.

```python
from __future__ import annotations

import yaml
from pathlib import Path
from typing import Dict
from dataclasses import dataclass

from core.logger import logger
from schemas.agent_registration import AgentRegistration

class AgentRegistry:
    """Encapsulates the state and logic for available specialist agents."""
    
    # def __init__(self):
    #     self._agents: Dict[str, AgentRegistration] = {}
    
    # =============== S I N G L E T O N ==============#
    # 1. Hold the single private instance at the class level
    # 1. Declare the type at the class level (like a C# property)
    _instance: AgentRegistry | None = None
    _agents: Dict[str, AgentRegistration]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AgentRegistry, cls).__new__(cls)
            
            # 2. Assign the value WITHOUT the inline type hint
            cls._instance._agents = {}
            
        return cls._instance
    

    def load_from_disk(self, skills_dir: str = "skills") -> None:
        """Clears and re-reads all SKILLS.md file targets from disk."""
        self._agents.clear()

        skills_path = Path(skills_dir)
        if not skills_path.exists():
            logger.warning("registry | target directory not found: %s", skills_dir)
            return

        for file_path in skills_path.glob("**/SKILL.md"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()

                if not content.startswith("---"):
                    continue

                parts = content.split("---", 2)
                if len(parts) < 3:
                    continue

                meta = yaml.safe_load(parts[1]) or {}
                key = meta.get("key")
                name = meta.get("name")

                if not key or not name:
                    continue

                self._agents[key] = AgentRegistration(
                    key=key,
                    name=name,
                    services=meta.get("services", []),
                    owns=meta.get("owns", ""),
                    description=meta.get("description", ""),
                    system_instructions=parts[2].strip()
                )
                logger.info("registry | compiled skill configuration target: %s", key)

            except Exception as e:
                logger.error("registry | structural parse failure at %s | error=%s", file_path, e)

    def get(self, key: str) -> AgentRegistration | None:
        """Safely retrieves an agent registration by key."""
        return self._agents.get(key)

    def has_specialist(self, key: str) -> bool:
        """Checks if a specialist exists in the registry."""
        return key in self._agents

    def build_prompt(self) -> str:
        """Compiles the dynamic layout string for injection into the supervisor prompt."""
        if not self._agents:
            return "Available Specialists:\n- None configured."

        lines = ["Available Specialists:"]
        for key, reg in self._agents.items():
            lines.append(f"- [{key}]: {reg.name} -> {reg.description} (Owns: {reg.owns})")
        return "\n".join(lines)

    def build_specialist(self, key: str, user_email: str):
        """Instantiates a stable SpecialistAgent using clean dependency injection."""
        from agents.specialist import SpecialistAgent

        registration = self.get(key)
        if not registration:
            raise ValueError(f"Specialist agent '{key}' is missing from runtime registry.")

        return SpecialistAgent(key=key, registration=registration, user_email=user_email)
---

## 5. `mcps/mcp_pool.py` — Full Implementation

Lazy cache keyed by `(user_email, services)`. No async. No lifecycle management.

```python
import os
from pydantic_ai.mcp import MCPServerStdio

from mcps.google import google_workspace_server

_servers: dict[str, MCPServerStdio] = {}


def get_pool_server(services: list[str], user_email: str) -> MCPServerStdio:
    """Return a cached MCPServerStdio for the given (user_email, services) pair.

    Constructs a new instance on first call for a given combination.
    Returns the cached instance on all subsequent calls.

    pydantic-ai manages the subprocess lifecycle when the agent runs.
    No explicit start/stop is needed here.
    """
    key = f"{user_email}:{'_'.join(sorted(services))}"
    if key not in _servers:
        _servers[key] = google_workspace_server(services, user_email)
    return _servers[key]
```

**Why a dict keyed by `(user_email, services)`?** Different specialists expose
different tool surfaces — the tasks agent only needs `["tasks"]`, the email agent
only needs `["mail"]`. A separate cache entry per combination means each agent
gets a server scoped to its own narrow tool surface. Two agents never share a
server with more tools than they need.

**Why not start the server in lifespan?** `MCPServerStdio` has no `.start()`
method. pydantic-ai manages the subprocess when `Agent.run()` executes. The pool
only needs to hold the configuration object — pydantic-ai does the rest.

---

## 6. `agents/specialist.py` — Full Implementation

Generic agent constructed entirely from an `AgentRegistration`. No subclasses
needed for MCP agents — the registration supplies everything.

```python
from __future__ import annotations

import os
from datetime import date
from typing import Any

from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from core.registry import AgentRegistration

from mcps.google import google_workspace_server
from mcps.mcp_pool import get_pool_server
from schemas.specialist_result import SpecialistResult

_factory = LLMFactory()


class SpecialistAgent(BaseAgent):
    """
    Generic specialist agent constructed from a registry entry.

    The registry entry supplies everything needed to build a functioning agent:
    - services   → which MCP tools to load (narrow tool surface)
    - owns       → injected into system prompt so the LLM knows its domain

    This class never changes when new agents are added. Only the registry
    entry and (if needed) the MCP server wiring change.

    For agents that require custom logic — non-MCP tools, multi-step workflows,
    unusual error handling — write a dedicated class and set agent_class in the
    registry entry. This class handles the common case.
    """

    def __init__(self, key: str, registration: AgentRegistration, user_email: str) -> None:
        super().__init__(name=key)
        self._key = key
        self._user_email = user_email

        self._agent = Agent(
            model=_factory.get_model(os.getenv("SPECIALIST_MODEL")),
            system_prompt=self._build_system_prompt(registration),
            output_type=SpecialistResult,
            deps_type=AgentDeps,
            toolsets=[get_pool_server(registration.services, user_email)],
            retries=3
            # toolsets=[
            #     google_workspace_server(
            #         registration.services,
            #         user_email=user_email,
            #     ),
            # ],
        )

    def _build_system_prompt(self, reg: AgentRegistration) -> str:
        today = date.today().isoformat()
        return (f"""
            Today's date is {today}.

            [IDENTITY]
            {reg.system_instructions}

            [GLOBAL OPERATIONAL RULES]
            1. Domain Integrity: Your scope is strictly limited to: {reg.owns}.
            2. Context Isolation: You will receive compound prompts. Mentally isolate and extract ONLY the parameters, dates, and entities that directly pertain to your domain ({reg.owns}). 
            3. Filtering Logic: If input text contains data or constraints irrelevant to your domain (e.g., meeting times when you manage tasks, or email addresses when you manage boards), discard that information entirely. Do not map foreign parameters into your tool arguments.
            4. Execution: Use all tools necessary to complete your domain-specific tasks. Act immediately.
            5. Missing Information: If the instruction lacks critical details specific to YOUR domain, do not guess. Flag the missing parameter clearly and do not call tools.
            6. Validation: Never invent IDs, names, or addresses. Before modifying/completing, search for exact matches. If not found, report what exists and do not act.
            7. Output: Log one actions_taken entry per tool call. Provide a concise summary of results.
        """                
        )

    def _log_messages(self, messages: list[Any]) -> None:
        for msg in messages:
            if isinstance(msg, ModelResponse):
                for part in msg.parts:
                    if isinstance(part, ToolCallPart):
                        logger.debug(
                            "SpecialistAgent[%s].tool_call | tool=%s | args=%r",
                            self._key, part.tool_name, part.args,
                        )
            elif isinstance(msg, ModelRequest):
                for part in msg.parts:
                    if isinstance(part, ToolReturnPart):
                        logger.debug(
                            "SpecialistAgent[%s].tool_result | tool=%s | content=%r",
                            self._key, part.tool_name, part.content,
                        )

    async def run(self, sub_task: str, deps: AgentDeps) -> SpecialistResult:
        logger.warning(
            "SpecialistAgent[%s].run | user=%s | email=%s | sub_task=%r",
            self._key, deps.user_id, self._user_email, sub_task,
        )

        # async with self._agent: # DONT USE THIS ANYWORE, GETTING FROM POOL
        result = await self._agent.run(
            user_prompt=sub_task,
            deps=deps,
        )

        self._log_messages(result.all_messages())

        usage = result.usage
        logger.warning(
            "SpecialistAgent[%s].usage | user=%s | input=%s | output=%s | total=%s",
            self._key, deps.user_id,
            usage.input_tokens,
            usage.output_tokens,
            usage.total_tokens,
        )
        output: SpecialistResult = result.output

        logger.warning(
            "SpecialistAgent[%s].result | user=%s | actions=%r | missing=%r",
            self._key, deps.user_id, output.actions_taken, output.missing_info,
        )
        return output
```

---

## 7. `agents/supervisor.py` — Full Implementation

Scans the registry at construction time. Delegates to specialists via
`build_specialist()`. The system prompt always reflects what is on disk.

```python
from __future__ import annotations

import os
from typing import Any, List

from pydantic_ai import Agent, RunContext
from pydantic_ai.messages import ModelResponse, ToolCallPart

from agents.base import BaseAgent

from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from core.registry import AgentRegistry

from schemas.specialist_result import SpecialistResult
from schemas.supervisor_response import SupervisorResponse

_factory = LLMFactory()


class SupervisorAgent(BaseAgent):
    """
    Entry point for all user requests.

    Makes two decisions:
    1. Does this request require tool use, or can it be answered directly?
    2. If tool use is needed, which specialists should handle it?

    The Supervisor reads the registry at startup. Its system prompt always reflects exactly what 
    specialists are available. Adding a new specialist to the registry is immediately visible 
    to the Supervisor — no code changes here.

    Never resolves user identity — AgentDeps arrives fully populated.
    Never calls MCP tools directly — that is the specialists' job.
    """

    def __init__(self) -> None:
        super().__init__(name="supervisor")

        # EXPLICIT STEP: Re-scan the skills directory straight from disk on initialization
        self._registry = AgentRegistry()

        self._registry.load_from_disk(skills_dir="skills")

        # Retained your precise framework keywords: output_type and deps_type
        self.agent = Agent(
            model=_factory.get_model(os.getenv("SUPERVISOR_MODEL")),
            system_prompt=self._build_system_prompt(),
            output_type=SupervisorResponse,
            deps_type=AgentDeps,
        )

        # Register the delegation tool explicitly
        self.agent.tool(self.delegate_to_specialists)

    def _build_system_prompt(self) -> str:
        """Dynamically pulls the instructions straight out of the loaded registry map."""
        registry_manifest = self._registry.build_prompt()
        
        return f"""
            You are the entry point for all user requests.
            Your system prompt always reflects exactly what specialists are available on disk.

            {registry_manifest}

            Guidelines:
            1. Determine if the user's request requires tool actions or can be answered directly.
            2. If tool execution is required, select the correct specialist keys and delegate tasks.
            3. Never attempt to resolve user credentials or call MCP platforms directly.
        """

    async def run(self, user_prompt: str, deps: AgentDeps) -> SupervisorResponse:
        logger.warning("SupervisorAgent.run | user=%s | prompt=%r", deps.user_id, user_prompt)
        result = await self.agent.run(user_prompt, deps=deps)

        return result.output

    async def delegate_to_specialists(
        self, 
        ctx: RunContext[AgentDeps], 
        specialist_keys: list[str], 
        sub_tasks: list[str]
    ) -> str:
        """Executes sequential handoffs to the dynamically verified disk specialists."""
        results: list[SpecialistResult] = []

        for key, sub_task in zip(specialist_keys, sub_tasks):
            if not self._registry.has_specialist(key):
                logger.error("SupervisorAgent | validation failed | unknown specialist key: %s", key)
                continue

            logger.warning("SupervisorAgent | delegating control | specialist=%s | task=%r", key, sub_task)
            
            # Build the specialist instance explicitly using the verified registry row
            specialist = self._registry.build_specialist(key, ctx.deps.user_email)
            
            # Direct execution pass down to the target specialist loop
            res = await specialist.run(sub_task, deps=ctx.deps)
            results.append(res)

        return self._format_specialist_results(results)

    def _format_specialist_results(self, results: list[SpecialistResult]) -> str:
        """
        The Supervisor's LLM receives this string as the tool return value.
        It uses the merged summary to compose the final user-facing message.

        Format:
        - Single result: return summary + actions directly.
        - Multiple results: prefix each block with the specialist index so the
          Supervisor can tell which actions came from which specialist.
        """
        if not results:
            return "No specialists returned results."

        if len(results) == 1:
            r = results[0]
            parts = [f"Summary: {r.summary}"]
            if r.actions_taken:
                parts.append("Actions taken:\n" + "\n".join(f"  - {a}" for a in r.actions_taken))
            if r.missing_info:
                parts.append(f"Missing info: {r.missing_info}")
            return "\n".join(parts)

        # Multiple specialists — label each block cleanly
        blocks = []
        for i, r in enumerate(results, start=1):
            lines = [f"[Specialist {i}] Summary: {r.summary}"]
            if r.actions_taken:
                lines.append("Actions:\n" + "\n".join(f"  - {a}" for a in r.actions_taken))
            blocks.append("\n".join(lines))

        return "\n\n".join(blocks)
```

---

## 8. `gateway/app.py` — Lifespan

The lifespan handler is unchanged from Stage 2 in terms of MCP concerns. It
does not start, stop, or reference workspace-mcp. It initialises SQLite and
constructs the supervisor. That is all.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _supervisor, _store

    if not _USER_EMAIL:
        raise RuntimeError("USER_GOOGLE_EMAIL is not set")
    if not _WEBHOOK_SECRET:
        raise RuntimeError("WEBHOOK_SECRET is not set")
    if not _ALLOWED_CHAT_ID:
        raise RuntimeError("TELEGRAM_CHAT_ID is not set")

    _store = SQLiteStore()
    await _store.initialise()          # creates agent_turns + reminders tables

    _supervisor = SupervisorAgent()    # scans skills/, builds AGENT_REGISTRY

    logger.info(
        "gateway | started | user=%s | email=%s | allowed_chat_id=%d",
        _USER_ID, _USER_EMAIL, _ALLOWED_CHAT_ID,
    )
    yield
    logger.info("gateway | shutdown")
```

Startup log sequence:

```
registry | compiled skill configuration target: tasks
registry | compiled skill configuration target: calendar
registry | compiled skill configuration target: email
registry | compiled skill configuration target: reminders
gateway | started | user=local_user | email=...
```

---

## 9. `agents/reminders.py` — Full Implementation

The reminder agent is the first tool agent. It calls Python functions directly
against SQLite. It has no MCP connection. Its `services` field in `SKILL.md`
is an empty list.

### SQLite schema addition

Add to `memory/sqlite_store.py` `initialise()`, after the `agent_turns` DDL:

```python
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

The `fired` column is 0 for all Stage 3a operations. Stage 4 APScheduler uses
it to track sent reminders. Adding it now avoids a schema migration later.

### Pydantic schema

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

### Tool functions

```python
import os
from datetime import datetime, timezone
import aiosqlite

_DB_PATH = os.getenv("SQLITE_PATH", "data/assistant.db")


async def create_reminder(text: str, remind_at: datetime) -> Reminder:
    """Store a new reminder. Returns the created record."""
    if remind_at.tzinfo is None:
        remind_at = remind_at.replace(tzinfo=timezone.utc)
    now = datetime.now(tz=timezone.utc)

    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO reminders (text, remind_at, created_at, fired) VALUES (?, ?, ?, 0)",
            (text, remind_at.isoformat(), now.isoformat()),
        )
        await db.commit()
        row_id = cursor.lastrowid

    return Reminder(id=row_id, text=text, remind_at=remind_at, created_at=now, fired=False)


async def list_reminders(include_past: bool = False) -> list[Reminder]:
    """Return upcoming reminders (or all if include_past=True), ordered by remind_at."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    async with aiosqlite.connect(_DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if include_past:
            cursor = await db.execute(
                "SELECT id, text, remind_at, created_at, fired FROM reminders ORDER BY remind_at ASC"
            )
        else:
            cursor = await db.execute(
                "SELECT id, text, remind_at, created_at, fired "
                "FROM reminders WHERE remind_at >= ? AND fired = 0 ORDER BY remind_at ASC",
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
    """Delete a reminder by ID. Returns True if found and deleted, False otherwise."""
    async with aiosqlite.connect(_DB_PATH) as db:
        cursor = await db.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await db.commit()
        return cursor.rowcount > 0
```

### RemindersAgent class

`RemindersAgent` is a peer of `SpecialistAgent`, not a subclass. It uses the
same `.run(sub_task, deps)` interface so the supervisor can call it identically.
The key difference: its tools are Python functions, not MCP tool calls.

`build_specialist()` in `registry.py` must special-case the `reminders` key to
construct a `RemindersAgent` instead of a `SpecialistAgent`:

```python
def build_specialist(key: str, user_email: str):
    from agents.specialist import SpecialistAgent
    from agents.reminders import RemindersAgent

    registration = AGENT_REGISTRY.get(key)
    if not registration:
        raise ValueError(f"Specialist agent '{key}' is missing from runtime registry.")

    if key == "reminders":
        return RemindersAgent(registration=registration)

    return SpecialistAgent(key=key, registration=registration, user_email=user_email)
```

```python
from __future__ import annotations

import os
import logging
from datetime import date

from pydantic_ai import Agent

from agents.reminders_tools import create_reminder, list_reminders, delete_reminder
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.registry import AgentRegistration
from schemas.specialist_result import SpecialistResult

logger = logging.getLogger("reminders_agent")
_factory = LLMFactory()


class RemindersAgent:
    """Tool agent for reminder management.

    Does not connect to workspace-mcp. Tools are Python functions operating
    on the local SQLite database. Uses the same .run(sub_task, deps) interface
    as SpecialistAgent so the supervisor can call it identically.
    """

    def __init__(self, registration: AgentRegistration) -> None:
        self._registration = registration

        self._agent = Agent(
            model=_factory.get_model(os.getenv("SPECIALIST_MODEL")),
            system_prompt=self._build_system_prompt(),
            output_type=SpecialistResult,
            deps_type=AgentDeps,
            retries=3,
        )
        self._agent.tool(create_reminder)
        self._agent.tool(list_reminders)
        self._agent.tool(delete_reminder)

    def _build_system_prompt(self) -> str:
        today = date.today().isoformat()
        base = f"Today's date is {today}. You are a specialist agent. You own: {self._registration.owns}\n\n"
        # Body from SKILL.md is in registration.owns for now — see Section 10
        return base

    async def run(self, sub_task: str, deps: AgentDeps) -> SpecialistResult:
        logger.warning("RemindersAgent.run | user=%s | sub_task=%r", deps.user_id, sub_task)
        result = await self._agent.run(user_prompt=sub_task, deps=deps)
        output: SpecialistResult = result.output
        logger.warning(
            "RemindersAgent.result | user=%s | actions=%r | missing=%r",
            deps.user_id, output.actions_taken, output.missing_info,
        )
        return output
```

---

## 10. Injecting SKILL.md Body into System Prompts

The `AgentRegistration` dataclass carries the metadata fields from the SKILL.md
frontmatter. To make the full body (behavioural instructions) available to agents,
extend `AgentRegistration` with a `instructions` field and populate it in
`load_registry_from_disk()`:

```python
from dataclasses import dataclass, field
from typing import List


@dataclass
class AgentRegistration:
    """The clean interface layer consumed directly by specialist.py and supervisor.py."""
    key: str
    name: str
    services: List[str] = field(default_factory=list)
    owns: str = ""
    description: str = ""

    # This will hold everything below the metadata '---'
    system_instructions: str = ""
```

Both `SpecialistAgent._build_system_prompt()` and `RemindersAgent._build_system_prompt()`
append `registration.instructions` to the base prompt:

```python
def _build_system_prompt(self, reg: AgentRegistration) -> str:
    today = date.today().isoformat()
    base = f"""
        Today's date is {today}. You are a specialist agent. You own: {reg.owns}
        ... (context isolation and rules as before) ...
    """
    if reg.instructions:
        base += f"\n\nSkill Instructions:\n{reg.instructions}"
    return base
```

---

## 11. File Layout After Stage 3a

```
project/
├── agents/
│   ├── base.py
│   ├── reminders.py            NEW
│   ├── reminders_tools.py    
│   ├── specialist.py           UPDATED
│   └── supervisor.py           UPDATED
├── core/
│   ├── deps.py
│   ├── llm_factory.py
│   ├── logger.py
│   └── registry.py             REWRITTEN
├── gateway/
│   ├── app.py                  unchanged from Stage 2
│   └── telegram_client.py
├── mcps/
│   ├── google.py
│   └── mcp_pool.py             UPDATED
├── memory/
│   ├── sqlite_store.py         UPDATED (reminders DDL added)
│   └── ...
├── schemas/
│   ├── specialist_result.py
│   ├── supervisor_response.py
│   ├── turn_record.py
│   └── agent_registration.py
├── skills/
│   ├── calendar/
│   │   └── SKILL.md            NEW
│   ├── email/
│   │   └── SKILL.md            NEW
│   ├── reminders/
│   │   └── SKILL.md            NEW
│   └── tasks/
│       └── SKILL.md            NEW
├── tools/
│   └── reminder_tools.py       NEW  (tool functions separated for testability)
├── main.py
└── .env
```

---

## 12. Implementation Order

### Phase 1 — Registry and skill files

1. Create the `skills/` directory.
2. Write all four `SKILL.md` files from Section 3.
3. Smoke test: start the app, confirm all four agents appear in startup logs.

### Phase 2 — Reminder agent

1. Add the `reminders` DDL to `memory/sqlite_store.py` `initialise()`.
2. Create `agents/reminders_tools.py` with the three tool functions from Section 9.
3. Create `agents/reminders.py` from Section 9.
4. Update `build_specialist()` in `registry.py` to special-case the `reminders` key.
5. Test via `python main.py`:

| Input | Expected |
|---|---|
| `Remind me to call David tomorrow at 3pm` | Confirmation with date and time |
| `What reminders do I have?` | Lists reminder with ID, text, and scheduled time |
| `Delete reminder 1` | Confirmation of deletion |
| `What reminders do I have?` | "You have no upcoming reminders." |

Verify SQLite state:
```powershell
sqlite3 data/assistant.db "SELECT id, text, remind_at, fired FROM reminders;"
```

### Phase 3 — System prompt injection

1. Update `SpecialistAgent._build_system_prompt()` to append `reg.instructions`.
2. Update `RemindersAgent._build_system_prompt()` to append `registration.instructions`.
3. Confirm the skill body appears in agent behaviour — create a task and verify
   the agent follows the instructions from the SKILL.md body.

### Phase 4 — New agent discovery test

Create a dummy skill file and confirm the registry picks it up without any code change:

```powershell
mkdir skills\test_agent
@"
---
key: "test_agent"
name: "test_agent"
services: ["tasks"]
owns: "nothing"
description: "Temporary test agent for discovery validation."
---
This agent does nothing. It exists to test registry discovery.
"@ | Out-File skills\test_agent\SKILL.md -Encoding utf8
```

Restart. Expected log:
```
registry | compiled skill configuration target: test_agent
```

Remove the folder, restart, confirm it disappears.

### Phase 5 — Full integration test

```powershell
uvicorn gateway.app:app --reload
```

Expected startup logs:
```
registry | compiled skill configuration target: tasks
registry | compiled skill configuration target: calendar
registry | compiled skill configuration target: email
registry | compiled skill configuration target: reminders
gateway | started | user=local_user | email=...
```

Full Telegram smoke test:

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

Docker smoke test:
```powershell
docker compose up -d --build
curl http://localhost:10000/health
docker compose logs --tail=30
```

Expected: `{"status":"ok"}`, same startup log sequence in container.

---

## 13. Troubleshooting

**Registry empty at startup**

Confirm `skills/` exists at the project root (not inside `gateway/` or `agents/`).
Confirm each `SKILL.md` starts with `---` on the first line — no BOM, no blank
line before the delimiter. Confirm `key` and `name` fields are present in every
frontmatter block.

**Skill file not loaded**

`SKILL.md` is case-sensitive on Linux (Docker runs Linux). Confirm the filename
is exactly `SKILL.md`. Check for a `registry | structural parse failure` log line
which will include the path and the exception.

**Reminder agent not routed**

The supervisor's system prompt lists available specialists from `build_registry_prompt()`.
If `reminders` does not appear in that string, `load_registry_from_disk()` did not
load `skills/reminders/SKILL.md`. Check the file exists and is valid YAML. Confirm
`key: "reminders"` is in the frontmatter.

**`build_specialist()` raises ValueError**

The supervisor is attempting to delegate to a key that is not in `AGENT_REGISTRY`.
This means the `SKILL.md` for that key was not loaded at startup — either the file
is missing, malformed, or the key in frontmatter does not match what the supervisor
is routing to. Check startup logs for `registry | compiled skill configuration target: <key>`.

**Stage 2 Telegram flow broken**

The supervisor's routing depends on the `description` field in each SKILL.md being
clear and accurate. If the supervisor stops routing to `tasks`, `calendar`, or
`email`, check the description field — it must clearly state what the agent handles.
Check that all three keys appear in startup logs.

**SQLite schema error on reminders table**

Delete `data/assistant.db` and restart — `initialise()` will recreate all tables.
Do not delete the database if it contains data you want to keep; run the DDL manually:

```powershell
sqlite3 data/assistant.db "CREATE TABLE IF NOT EXISTS reminders (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, remind_at TEXT NOT NULL, created_at TEXT NOT NULL, fired INTEGER NOT NULL DEFAULT 0);"
```

---

## 14. How Stage 3b Builds on This

Stage 3a establishes how agents are built and discovered. Nothing in Stage 3a
changes in Stage 3b.

Stage 3b enriches agents with knowledge of who they are and who they are talking
to. Two new markdown files are loaded at startup:

- `memory/agents/<key>.md` — each agent's persona: tone, style, boundaries.
- `memory/brain/user.md` — facts about you: timezone (MYT), preferred deadline
  day, contact name shortcuts, email preferences.

A `memory/markdown_store.py` loader reads these files at startup. Each agent's
`_build_system_prompt()` gains a second injection point alongside `instructions`.

The registry, `mcp_pool`, `SpecialistAgent`, `RemindersAgent`, and `gateway/app.py`
do not change in Stage 3b.

---

## 15. Done When

- App starts and logs all four skill configuration targets in the correct sequence
- All four agents registered: `tasks`, `calendar`, `email`, `reminders`
- Each agent's system prompt includes its `SKILL.md` body
- A new `SKILL.md` dropped into `skills/` is discovered and registered on restart without any code change
- Reminder create, list, and delete work via both CLI and Telegram
- All Stage 2 smoke tests pass unchanged
- `python main.py` CLI loop still works for all four agent types
- `docker compose up -d --build` produces a working container with the same startup log sequence