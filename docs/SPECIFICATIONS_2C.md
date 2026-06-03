# Personal Telegram Assistant
## Specification — Stage 2C: Conversation History, New Integrations & Personal Notes Agent

> **Assumes:** Stage 2B (SPECIFICATIONS_2B.md) complete and merged to `main` —
> the registry scans `skills/` at startup, `SpecialistAgent` is constructed from
> `AgentRegistration`, `mcp_pool` is a lazy cache, `SupervisorAgent` delegates
> via `build_specialist()`. All Stage 2B smoke tests pass. The full Telegram
> webhook flow is stable.
>
> **Branch:** `stage/2c` branched from `main` after Stage 2B merge
>
> **Done when:** Every Telegram exchange is aware of prior turns in the same
> session. The assistant can act on `gmail`, `calendar` (Google official MCP),
> and `trello`. The `personal_notes` agent and `reminders` agent are both fully
> implemented and registered via `SKILL.md`. The `/assistant` debug endpoint
> maintains its own independent history from the Telegram webhook path. All
> Stage 2B smoke tests still pass unchanged.

---

## 1. What Stage 2C Adds

Stage 3a delivered a disk-driven registry and a working specialist factory. Every
agent is a file drop — no code change needed to add a new capability. The system
is structurally sound.

What it still lacks is memory within a session. Each Telegram message arrives as
if the conversation has never happened. The supervisor has no idea what it said
ten seconds ago. A follow-up like "when is it due?" fails because the prior
context — which task, which list — was never carried forward.

Stage 2C fixes that and adds three new service integrations:

**Problem 1 — Stateless conversation.** Every call to `_supervisor.run()` starts
a blank pydantic-ai context. Follow-up questions, pronouns, and references to
previous results all fail.

**Fix:** `SupervisorAgent.run()` accepts and forwards `message_history`. The
caller (`_process` in `app.py`) accumulates history from `result.all_messages()`
after each turn and passes it back on the next call. History lives in-memory for
the lifetime of the FastAPI process — no database involvement in Stage 2C.

**Problem 2 — Google Tasks is unreliable.** The `workspace-mcp` third-party
package does not consistently return the `due` field. Google's official Workspace
MCP server (in public preview from May 2026) covers Gmail and Calendar but not
Tasks. Tasks is dropped.

**Fix:** Replace with Trello for task and project management. Trello has a stable
REST API and a maintained MCP server. Google Tasks SKILL.md is retired.

**Problem 3 — Gmail and Calendar were relying on `workspace-mcp`.** Google now
publishes official remote MCP servers for Gmail and Calendar. These are
Google-managed, enterprise-ready, and eliminate the third-party dependency.

**Fix:** Gmail and Calendar skills are re-wired to use Google's official remote
MCP endpoints. `mcp_pool.py` gains a routing layer: `server_type: "google_remote"`
dispatches to `MCPServerHTTP`, `server_type: "stdio"` dispatches to
`MCPServerStdio` (for Trello), `server_type: "none"` returns `None` (for tool
agents like `personal_notes`).

**Problem 4 — `PersonalNoteAgent` is not in the registry.** It exists as
`agents/personal_notes.py` and works, but it is wired in by a hardcoded
`build_specialist()` branch. It does not have a `SKILL.md` file.

**Fix:** Add `skills/personal_notes/SKILL.md` with `agent_class: "PersonalNoteAgent"`
and `module_path: "agents.personal_notes"`. The registry dynamic-import path
handles construction. No special-case branching needed.

**What changes at the code level:**

| File | Change |
|---|---|
| `agents/supervisor.py` | UPDATED — `run()` accepts and returns `message_history` |
| `agents/reminders.py` | NEW — `RemindersAgent` full implementation |
| `agents/personal_notes.py` | NEW — `PersonalNoteAgent` full implementation |
| `tools/personal_notes_tools.py` | NEW — `save_as_txt` tool function |
| `gateway/app.py` | UPDATED — `_process` and `/assistant` accumulate and pass history |
| `mcps/mcp_pool.py` | UPDATED — routes by `server_type`, supports `google_remote` and `stdio` |
| `mcps/google_remote.py` | NEW — `MCPServerHTTP` factory for Google official MCP endpoints |
| `mcps/trello.py` | NEW — `MCPServerStdio` factory for Trello MCP server |
| `schemas/agent_registration.py` | unchanged — `server_type` field already present |
| `skills/gmail/SKILL.md` | UPDATED — `server_type: "google_remote"`, services adjusted |
| `skills/calendar/SKILL.md` | UPDATED — `server_type: "google_remote"`, services adjusted |
| `skills/trello/SKILL.md` | NEW — Trello board, card, and list management |
| `skills/personal_notes/SKILL.md` | NEW — registers `PersonalNoteAgent` via registry |
| `skills/reminders/SKILL.md` | NEW — registers `RemindersAgent` via registry |
| `skills/tasks/SKILL.md` | DELETED — Google Tasks retired |
| `memory/sqlite_store.py` | UPDATED — reminders DDL added |

**What does not change:**

`agents/specialist.py`, `core/registry.py`, `schemas/specialist_result.py`,
`schemas/supervisor_response.py`, `gateway/telegram_client.py` — none of these
are touched.

---

## 2. Architecture

### Conversation History — How It Works

pydantic-ai's `Agent.run()` accepts a `message_history` parameter. When provided,
it prepends the prior messages to the conversation before sending to the LLM.
`result.all_messages()` returns the full conversation including the new turn.

The pattern:

```
Turn 1:  supervisor.run(prompt, history=[])
         → result.all_messages() = [user_msg_1, assistant_msg_1, tool_calls_1, ...]
         → store as _message_history

Turn 2:  supervisor.run(prompt, history=_message_history)
         → LLM sees full prior context
         → result.all_messages() = [all_of_turn_1..., user_msg_2, assistant_msg_2, ...]
         → replace _message_history
```

This is entirely in-memory. `_message_history` is a module-level list in
`gateway/app.py`. It resets on process restart. Persistence across restarts is
Stage 3b (SQLite-backed history).

History grows with each turn. The `MAX_HISTORY_TURNS` constant (default: 10)
controls how many turns are passed. `_process` does not slice the history in
Stage 2C — the full accumulated list from `result.all_messages()` is passed back.
If token pressure becomes an issue that is a Stage 3b concern.

### Two History Lists — Why

The `/assistant` HTTP endpoint and the `/webhook` Telegram path both call
`_supervisor.run()`. If they share a single history list, a test via `/assistant`
will inject foreign context into the Telegram conversation.

Two separate module-level lists solve this with no complexity:

```python
_message_history: list = []           # Telegram webhook path
_assistant_history: list = []         # /assistant debug endpoint
```

Each path reads and writes only its own list. The supervisor is stateless —
it receives history as a parameter and returns the updated list as part of its
return value.

### `SupervisorAgent.run()` Return Contract

The supervisor now returns a tuple instead of a bare `SupervisorResponse`. This
is the clean design — no state on the supervisor instance, no attribute hacks:

```python
async def run(
    self,
    user_prompt: str,
    deps: AgentDeps,
    message_history: list | None = None,
) -> tuple[SupervisorResponse, list]:
    result = await self.agent.run(
        user_prompt, deps=deps, message_history=message_history or []
    )
    logger.warning("SupervisorAgent reply: %s", result.output)
    return result.output, result.all_messages()
```

Callers unpack:

```python
response, _message_history = await _supervisor.run(text, deps, message_history=_message_history)
```

### `SupervisorAgent.delegate_to_specialist()` Return List of SpecialistResults
```python
    async def delegate_to_specialists(
        self, 
        ctx: RunContext[AgentDeps], 
        specialist_keys: list[str], 
        sub_tasks: list[str]
    ) -> list[SpecialistResult]:
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
            print(f"DEBUG: Specialist returned {len(results)} results")
            results.append(res)

        logger.warning(f"DEBUG: Final results list count: {len(results)}")
        return results
```


### MCP Routing — How `server_type` Works

`AgentRegistration` already carries `server_type`. `mcp_pool.get_pool_server()`
reads it and dispatches:

| `server_type` | Dispatch | Used by |
|---|---|---|
| `"google_remote"` | `MCPServerHTTP` via `mcps/google_remote.py` | gmail, calendar |
| `"stdio"` | `MCPServerStdio` via `mcps/trello.py` | trello |
| `"none"` | returns `None` | personal_notes, reminders |

When `get_pool_server()` returns `None`, `SpecialistAgent.__init__()` sets
`toolsets=[]`. This is already handled in the current code:

```python
server = get_pool_server(registration, user_email)
toolsets = [server] if server is not None else []
```

No change needed in `specialist.py`.

### How a Request Flows

```
+-------------------------------------------------------------+
| Telegram Message                                            |
+-------------------------------------------------------------+
              │
              ▼
+-------------------------------------------------------------+
| FastAPI _process() (Background Task)                        |
|   reads:  _message_history                                  |
+-------------------------------------------------------------+
              │
              ▼
+-------------------------------------------------------------+
| SupervisorAgent.run(prompt, deps, message_history)          |
|   pydantic-ai sees full prior context                       |
|   returns: (SupervisorResponse, updated_messages)           |
+-------------------------------------------------------------+
              │ unpacks tuple
              ▼
+-------------------------------------------------------------+
| _process() stores result.all_messages() → _message_history |
| sends Telegram reply                                        |
| writes TurnRecord to SQLite                                 |
+-------------------------------------------------------------+
              │ (on delegation)
              ▼
+-------------------------------------------------------------+
| AgentRegistry.build_specialist(key, user_email)             |
|   dynamic import from module_path / agent_class             |
+-------------------------------------------------------------+
              │
              ▼
+---------------------------------------+--------------------+
| SpecialistAgent                       | PersonalNoteAgent  |
| (gmail, calendar, trello)             | (personal_notes)   |
+---------------------------------------+--------------------+
              │                                   │
              ▼                                   ▼
  get_pool_server()                      tools=[save_as_txt]
  → MCPServerHTTP (google_remote)        toolsets=[]
  → MCPServerStdio (stdio/trello)
  → None (none)
```

---

## 3. `SKILL.md` Format — Stage 2C Extensions

The `SKILL.md` format from Stage 3a is unchanged. Stage 2C uses two fields that
were already present in `AgentRegistration` but unused in skill files:
`server_type`, `agent_class`, and `module_path`.

### Frontmatter fields — full reference

| Field | Required | Type | Description |
|---|---|---|---|
| `key` | yes | string | Unique agent identifier. Lowercase, no spaces. |
| `name` | yes | string | Human-readable display name. Used in logs. |
| `services` | yes | list[str] | Service names passed to `get_pool_server()`. Empty list for tool agents. |
| `owns` | yes | string | Domain description injected into system prompt. |
| `description` | yes | string | One-line routing hint for the supervisor. |
| `server_type` | yes | string | MCP routing: `"google_remote"`, `"stdio"`, or `"none"`. |
| `agent_class` | no | string | Python class name. Defaults to `"SpecialistAgent"` if omitted. |
| `module_path` | no | string | Python module path. Defaults to `"agents.specialist"` if omitted. |

---

## 4. SKILL.md Files

### `skills/gmail/SKILL.md`

```markdown
---
key: "gmail"
name: "gmail"
owns: "Gmail email management"
description: "Handles reading, searching, drafting, and sending emails via Gmail."
server_type: "google_remote"
services: ["gmail"]
available: True
---
You are a Gmail specialist. You read, search, draft, and send emails on behalf of the user.

Guidelines:
1. Extraction: Extract recipients, subject, and body from the instruction. Never guess an email address.
2. Missing Information: If a recipient address is not explicitly stated, flag it as missing_info and do not send.
3. Drafts vs Send: Unless the user explicitly says "send", create a draft. Confirm before sending.
4. Search: When searching, use the most specific query terms available from the instruction.
5. Output: Log one actions_taken entry per tool call. Summarise what was read, sent, or drafted.
```

### `skills/calendar/SKILL.md`

```markdown
---
key: "calendar"
name: "calendar"
owns: "Google Calendar event management"
description: "Handles creating, reading, updating, and deleting calendar events."
server_type: "google_remote"
services: ["calendar"]
available: True
---
You are a Google Calendar specialist. You create, read, update, and delete calendar events.

Guidelines:
1. Extraction: Extract event title, date, time, duration, and attendees from the instruction.
2. Timezone: The user's timezone is MYT (UTC+8). Always store and display times in MYT.
3. Missing Information: If a date or time is missing or ambiguous, flag it in missing_info. Do not create events with assumed times.
4. Conflicts: If asked to check availability, list existing events in the requested window before confirming.
5. Output: Log one actions_taken entry per tool call. Confirm the event title, date, and time in your summary.
```

### `skills/trello/SKILL.md`

```markdown
---
key: "trello"
name: "trello"
owns: "Trello board, list, and card management"
description: "Handles creating, viewing, updating, and moving cards across Trello boards and lists."
server_type: "stdio"
services: ["trello"]
---
You are a Trello specialist. You manage boards, lists, and cards.

Guidelines:
1. Extraction: Extract the board name, list name, card title, description, and due date from the instruction.
2. Board Resolution: Always resolve the board name before acting. If the user refers to a board by a short name or alias, search for the closest match and confirm before modifying.
3. Missing Information: If a target list or board is not specified for a card creation or move, flag it in missing_info.
4. Due Dates: Accept natural language dates and convert to ISO 8601 before passing to tools. The user's timezone is MYT (UTC+8).
5. Output: Log one actions_taken entry per tool call. Confirm the card title, board, and list in your summary.
```

### `skills/reminders/SKILL.md`

```markdown
---
key: "reminders"
name: "reminders"
owns: "Personal reminder management"
description: "Stores and retrieves personal reminders with a date and time. Does not send proactive messages."
server_type: "none"
services: []
agent_class: "RemindersAgent"
module_path: "agents.reminders"
---
You are a reminder specialist. You store, list, and delete personal reminders.

Guidelines:
1. When storing a reminder, always confirm the exact text and the scheduled time before acting.
2. If the user does not specify a time, ask — never assume.
3. When listing reminders, show each one with its ID, text, and scheduled time.
4. When deleting, confirm the ID and text of what was deleted.
5. This agent stores and retrieves only. It does not send proactive Telegram messages. Tell the user their reminder is saved and that proactive delivery is coming in a future stage.

Edge Cases:
- Ambiguous times ("tomorrow morning") — ask for clarification.
- If the user asks to delete a reminder that does not exist, say so clearly.
- If the reminders list is empty, say "You have no upcoming reminders."
```

### `skills/personal_notes/SKILL.md`

```markdown
---
key: "personal_notes"
name: "personal_notes"
owns: "Personal note saving to local file system"
description: "Saves personal notes, memos, and freeform text to local .txt files."
server_type: "none"
services: []
agent_class: "PersonalNoteAgent"
module_path: "agents.personal_notes"
---
You are a personal notes specialist. You save freeform notes, memos, and text to local files.

Guidelines:
1. Content Required: The note content is mandatory. If the instruction contains no content to save, flag it in missing_info and do not call save_as_txt.
2. Filename: If the user specifies a filename, use it exactly. If not, generate a descriptive lowercase filename with underscores and today's date suffix (e.g., meeting_notes_2026-06-02.txt).
3. No Interpretation: Save exactly what the user provides. Do not summarise, reformat, or add content.
4. Confirmation: After saving, report the filename and character count in your summary.
```

---

## 5. `schemas/agent_registration.py` — Full Implementation

`server_type` must be present and populated from the SKILL.md frontmatter. This
is the field that drives MCP routing in `mcp_pool.py`.

```python
from dataclasses import dataclass, field
from typing import List


@dataclass
class AgentRegistration:
    """
    Unified data contract for agent configurations.
    All fields map directly to SKILL.md frontmatter keys.
    """
    key: str
    name: str
    services: List[str] = field(default_factory=list)
    owns: str = ""
    description: str = ""
    system_instructions: str = ""
    agent_class: str = "SpecialistAgent"
    module_path: str = "agents.specialist"
    server_type: str = "google"         # "google_remote" | "stdio" | "none"
    mcp_command: str = ""
    mcp_args: List[str] = field(default_factory=list)
    mcp_env_keys: List[str] = field(default_factory=list)

    # a flag to load agent or to skip
    available: bool = False
```

---

## 6. `core/registry.py` — Full Implementation

`server_type` must be read from the SKILL.md frontmatter and passed into
`AgentRegistration`. Without this, `mcp_pool.get_pool_server()` raises
`AttributeError: 'AgentRegistration' object has no attribute 'server_type'`.

```python
from __future__ import annotations

import yaml
import importlib
from pathlib import Path
from typing import Dict
from agents.protocol import SpecialistProtocol

from core.logger import logger
from schemas.agent_registration import AgentRegistration


class AgentRegistry:

    _instance: AgentRegistry | None = None
    _agents: Dict[str, AgentRegistration]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AgentRegistry, cls).__new__(cls)
            cls._instance._agents = {}
        return cls._instance

    def load_from_disk(self, skills_dir: str = "skills") -> None:
        """Clears and re-reads all SKILL.md targets from disk."""
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
                meta = yaml.safe_load(parts[1]) or {}
                # --- NEW: Skip if explicitly marked as not available ---
                if meta.get("available", True) is False:
                    logger.debug("registry | skipping unavailable skill at %s", file_path)
                    continue

                key = meta.get("key")
                name = meta.get("name")

                if not key or not name:
                    continue

                raw_module = meta.get("module_path")
                module_path = raw_module if (raw_module and raw_module.strip()) else "agents.specialist"

                raw_class = meta.get("agent_class")
                agent_class = raw_class if (raw_class and raw_class.strip()) else "SpecialistAgent"

                self._agents[key] = AgentRegistration(
                    key=key,
                    name=name,
                    services=meta.get("services", []),
                    owns=meta.get("owns", ""),
                    description=meta.get("description", ""),
                    system_instructions=parts[2].strip(),
                    agent_class=agent_class,
                    module_path=module_path,
                    server_type=meta.get("server_type", "google"),
                )
                logger.info("registry | compiled skill configuration target: %s", key)

            except Exception as e:
                logger.error("registry | structural parse failure at %s | error=%s", file_path, e)

    def get(self, key: str) -> AgentRegistration | None:
        return self._agents.get(key)

    def has_specialist(self, key: str) -> bool:
        return key in self._agents

    def build_prompt(self) -> str:
        if not self._agents:
            return "Available Specialists:\n- None configured."
        lines = ["Available Specialists:"]
        for key, reg in self._agents.items():
            lines.append(f"- [{key}]: {reg.name} -> {reg.description} (Owns: {reg.owns})")
        return "\n".join(lines)

    def build_specialist(self, key: str, user_email: str) -> SpecialistProtocol:
        registration = self.get(key)
        if not registration:
            raise ValueError(f"Agent '{key}' missing.")
        module = importlib.import_module(registration.module_path)
        agent_cls = getattr(module, registration.agent_class)
        return agent_cls(key=key, registration=registration, user_email=user_email)
```

---

## 7. `agents/specialist.py` — Full Implementation

```python
from __future__ import annotations

import os
from datetime import date
from typing import Any

from pydantic_ai import Agent, UsageLimits
from pydantic_ai.messages import ModelRequest, ModelResponse, ToolCallPart, ToolReturnPart

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from schemas.agent_registration import AgentRegistration
from mcps.mcp_pool import get_pool_server
from schemas.specialist_result import SpecialistResult

_factory = LLMFactory()


class SpecialistAgent(BaseAgent):

    def __init__(self, key: str, registration: AgentRegistration, user_email: str) -> None:
        super().__init__(name=key)
        self._key = key
        self._user_email = user_email

        server = get_pool_server(registration, user_email)
        toolsets = [server] if server is not None else []

        self._agent = Agent(
            model=_factory.get_model(os.getenv("SPECIALIST_MODEL")),
            system_prompt=self._build_system_prompt(registration),
            output_type=SpecialistResult,
            deps_type=AgentDeps,
            toolsets=toolsets,
        )

    def _build_system_prompt(self, reg: AgentRegistration) -> str:
        today = date.today().isoformat()
        return f"""
            Today's date is {today}.

            [IDENTITY]
            {reg.system_instructions}

            [GLOBAL OPERATIONAL RULES]
            1. Domain Integrity: Your scope is strictly limited to: {reg.owns}.
            2. Validation First: BEFORE calling any tool, verify the request provides all
               parameters necessary for your domain-specific tools to perform a deterministic action.
            3. Ambiguity & Missing Information:
               - If the request is vague or lacks required details, DO NOT call any tools.
               - If any required parameter is missing, DO NOT call any tools.
               - IMMEDIATELY populate 'missing_info' with a clear request for the missing item and return.
            4. Execution: Only call tools if you have 100% of the required parameters.
            5. Output: Log one actions_taken entry per tool call. Provide a concise summary of results.
        """

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
                        logger.warning(
                            "RAW_TOOL_DEBUG | tool=%s | raw_content=%s",
                            part.tool_name, part.content,
                        )
                        logger.debug(
                            "SpecialistAgent[%s].tool_result | tool=%s | content=%r",
                            self._key, part.tool_name, part.content,
                        )

    async def run(self, sub_task: str, deps: AgentDeps) -> SpecialistResult:
        logger.warning(
            "SpecialistAgent[%s].run | user=%s | email=%s | sub_task=%r",
            self._key, deps.user_id, self._user_email, sub_task,
        )

        result = await self._agent.run(
            user_prompt=sub_task,
            deps=deps,
            usage_limits=UsageLimits(request_limit=None),
        )

        self._log_messages(result.all_messages())

        usage = result.usage
        logger.warning(
            "SpecialistAgent[%s].usage | user=%s | input=%s | output=%s | total=%s",
            self._key, deps.user_id,
            usage.input_tokens, usage.output_tokens, usage.total_tokens,
        )

        output: SpecialistResult = result.output
        logger.warning(
            "SpecialistAgent[%s].result | user=%s | actions=%r | missing=%r",
            self._key, deps.user_id, output.actions_taken, output.missing_info,
        )
        return output
```

---

## 8. `agents/supervisor.py` — Full Implementation

```python
from __future__ import annotations

import os

from pydantic_ai import Agent, RunContext

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from core.registry import AgentRegistry
from schemas.specialist_result import SpecialistResult
from schemas.supervisor_response import SupervisorResponse

_factory = LLMFactory()


class SupervisorAgent(BaseAgent):

    def __init__(self) -> None:
        super().__init__(name="supervisor")

        self._registry = AgentRegistry()
        self._registry.load_from_disk(skills_dir="skills")

        self.agent = Agent(
            model=_factory.get_model(os.getenv("SUPERVISOR_MODEL")),
            system_prompt=self._build_system_prompt(),
            output_type=SupervisorResponse,
            deps_type=AgentDeps,
        )

        self.agent.tool(self.delegate_to_specialists)

    def _build_system_prompt(self) -> str:
        registry_manifest = self._registry.build_prompt()
        return f"""
            You are the entry point for all user requests.
            Your responsibility is to map user intent to specialist tools.

            {registry_manifest}

            Guidelines:
            1. Analyze user intent first.
            2. If a specific tool is required, select the specialist key and use 'delegate_to_specialists'.
            3. If the user's intent is ambiguous, conversational, or does not clearly map to any
               registered specialist:
               - DO NOT delegate.
               - Set 'requires_followup' to True.
               - Populate 'message' with a response that asks the user to clarify their intent.
            4. Never attempt to resolve credentials or call MCP platforms directly.

            [FLOW CONTROL RULES]
            - CASE A: If the request is unresolvable or 'missing_info' is returned, YOU ARE NOT FINISHED.
              * Set 'requires_followup' = True.
              * Draft a 'message' that clarifies the ambiguity.

            - CASE B: If a specialist execution returns a successful summary, YOU ARE FINISHED.
              * Set 'requires_followup' = False.
              * Summarize the outcome in the 'message' field.
        """

    async def run(
        self,
        user_prompt: str,
        deps: AgentDeps,
        message_history: list | None = None,
    ) -> tuple[SupervisorResponse, list]:
        logger.warning("SupervisorAgent.run | user=%s | prompt=%r", deps.user_id, user_prompt)
        result = await self.agent.run(
            user_prompt, deps=deps, message_history=message_history or []
        )
        logger.warning("SupervisorAgent reply: %s", result.output)
        return result.output, result.all_messages()

    async def delegate_to_specialists(
        self,
        ctx: RunContext[AgentDeps],
        specialist_keys: list[str],
        sub_tasks: list[str],
    ) -> list[SpecialistResult]:
        """Executes sequential handoffs to the dynamically verified disk specialists."""
        results: list[SpecialistResult] = []

        for key, sub_task in zip(specialist_keys, sub_tasks):
            if not self._registry.has_specialist(key):
                logger.error("SupervisorAgent | validation failed | unknown specialist key: %s", key)
                continue

            logger.warning(
                "SupervisorAgent | delegating control | specialist=%s | task=%r", key, sub_task
            )

            specialist = self._registry.build_specialist(key, ctx.deps.user_email)
            res = await specialist.run(sub_task, deps=ctx.deps)
            results.append(res)

        return results
```

---

Only `run()` changes. Everything else — `__init__`, `_build_system_prompt`,
`delegate_to_specialists` — is unchanged from Stage 3a.

```python
async def run(
    self,
    user_prompt: str,
    deps: AgentDeps,
    message_history: list | None = None,
) -> tuple[SupervisorResponse, list]:
    logger.warning("SupervisorAgent.run | user=%s | prompt=%r", deps.user_id, user_prompt)
    result = await self.agent.run(
        user_prompt, deps=deps, message_history=message_history or []
    )
    logger.warning("SupervisorAgent reply: %s", result.output)
    return result.output, result.all_messages()
```

The return type changes from `SupervisorResponse` to `tuple[SupervisorResponse, list]`.
All callers must be updated to unpack the tuple.

---

## 6. `gateway/app.py` — Changes

### Module-level history lists

Add below the existing module-level state declarations:

```python
_message_history: list = []      # Telegram webhook path
_assistant_history: list = []    # /assistant debug endpoint
```

### `_process()` — updated

```python
async def _process(chat_id: int, text: str) -> None:
    global _message_history
    async with _agent_lock:
        deps = AgentDeps(
            user_id=_USER_ID,
            user_email=_USER_EMAIL,
        )

        try:
            response, _message_history = await _supervisor.run(
                text,
                deps=deps,
                message_history=_message_history,
            )
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

### `/assistant` endpoint — updated

```python
@app.post("/assistant/id/{chat_id}/msg/{chat}")
async def assistant(chat_id: int, chat: str) -> dict:
    global _assistant_history
    deps = AgentDeps(
        user_id=_USER_ID,
        user_email=_USER_EMAIL,
    )
    try:
        response, _assistant_history = await _supervisor.run(
            chat,
            deps=deps,
            message_history=_assistant_history,
        )
    except Exception:
        logger.exception("webhook | agent loop failed | chat_id=%d", chat_id)
        return {"ok": True}

    return {"message": response.message}
```

The two history lists are intentionally separate. Using the `/assistant` endpoint
for testing does not pollute the Telegram conversation history.

---

## 7. `mcps/mcp_pool.py` — Full Implementation

Routes by `server_type` from `AgentRegistration`. Returns `None` for `"none"`.

```python
from __future__ import annotations

from pydantic_ai.mcp import MCPServerStdio

from mcps.google_remote import google_remote_server
from mcps.trello import trello_server
from schemas.agent_registration import AgentRegistration

_servers: dict[str, object] = {}


def get_pool_server(registration: AgentRegistration, user_email: str) -> object | None:
    """Return a cached MCP server instance for the given registration and user.

    Routes by registration.server_type:
      "google_remote" → MCPServerHTTP (Google official remote MCP)
      "stdio"         → MCPServerStdio (local subprocess, e.g. Trello)
      "none"          → None (tool agents: personal_notes, reminders)

    Returns None for server_type "none". SpecialistAgent handles None by
    setting toolsets=[].
    """
    if registration.server_type == "none" or not registration.services:
        return None

    cache_key = f"{user_email}:{registration.server_type}:{'_'.join(sorted(registration.services))}"

    if cache_key not in _servers:
        if registration.server_type == "google_remote":
            _servers[cache_key] = google_remote_server(registration.services, user_email)
        elif registration.server_type == "stdio":
            _servers[cache_key] = _build_stdio_server(registration, user_email)

    return _servers.get(cache_key)


def _build_stdio_server(registration: AgentRegistration, user_email: str) -> MCPServerStdio:
    """Dispatch stdio server construction by service name."""
    if "trello" in registration.services:
        return trello_server(user_email)
    raise ValueError(f"No stdio server factory for services: {registration.services}")
```

---

## 8. `mcps/google_remote.py` — New File

Google's official remote Workspace MCP servers. Each service has a dedicated
endpoint. Authentication is handled via OAuth 2.0 — the same credentials already
configured for the Google Cloud project.

```python
from __future__ import annotations

import os
from pydantic_ai.mcp import MCPServerHTTP


# Google official Workspace MCP endpoints (public preview, May 2026)
_GMAIL_ENDPOINT = "https://gmail.googleapis.com/mcp/v1"
_CALENDAR_ENDPOINT = "https://calendar.googleapis.com/mcp/v1"

_SERVICE_ENDPOINTS: dict[str, str] = {
    "gmail": _GMAIL_ENDPOINT,
    "calendar": _CALENDAR_ENDPOINT,
}


def google_remote_server(services: list[str], user_email: str) -> MCPServerHTTP:
    """Return an MCPServerHTTP for the given Google Workspace service.

    Only one service per call — each Google service has its own dedicated
    remote endpoint. If multiple services are requested, use the first one.
    The pool creates separate cache entries per service.

    Args:
        services: list of service names, e.g. ["gmail"] or ["calendar"]
        user_email: the authenticated user's Google email address

    Returns:
        MCPServerHTTP configured for the requested service endpoint.

    Raises:
        ValueError: if the service name is not a known Google remote service.
    """
    service = services[0]
    endpoint = _SERVICE_ENDPOINTS.get(service)
    if not endpoint:
        raise ValueError(
            f"No Google remote MCP endpoint for service: '{service}'. "
            f"Known services: {list(_SERVICE_ENDPOINTS.keys())}"
        )

    token = os.getenv("GOOGLE_ACCESS_TOKEN", "")

    return MCPServerHTTP(
        url=endpoint,
        headers={
            "Authorization": f"Bearer {token}",
            "X-Goog-User-Project": os.getenv("GOOGLE_CLOUD_PROJECT", ""),
        },
    )
```

**Authentication note:** `GOOGLE_ACCESS_TOKEN` must be a valid OAuth 2.0 bearer
token for the authenticated user. In Stage 2C this is set as an environment
variable. Stage 3b will introduce token refresh logic. `GOOGLE_CLOUD_PROJECT`
is the Google Cloud project ID under which the Workspace APIs are enabled.

Add to `.env`:
```
GOOGLE_ACCESS_TOKEN=ya29.your_token_here
GOOGLE_CLOUD_PROJECT=your-project-id
```

---

## 9. `mcps/trello.py` — New File

Trello uses an MCP server running as a local subprocess via `uvx`. The Trello
MCP server is `@modelcontextprotocol/server-trello` (npm package).

```python
from __future__ import annotations

import os
from pydantic_ai.mcp import MCPServerStdio


def trello_server(user_email: str | None = None) -> MCPServerStdio:
    """Return a configured MCPServerStdio for the Trello MCP server.

    Authentication via Trello API key and token — set as environment variables.
    user_email is accepted for interface consistency but not used by Trello.

    Args:
        user_email: ignored, present for interface consistency with other factories.

    Returns:
        MCPServerStdio configured to spawn the Trello MCP server.
    """
    env = {**os.environ}
    env["TRELLO_API_KEY"] = os.getenv("TRELLO_API_KEY", "")
    env["TRELLO_TOKEN"] = os.getenv("TRELLO_TOKEN", "")

    return MCPServerStdio(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-trello"],
        env=env,
    )
```

Add to `.env`:
```
TRELLO_API_KEY=your_trello_api_key
TRELLO_TOKEN=your_trello_token
```

Trello API key and token are obtained from https://trello.com/app-key.

### 9A. Trello Authentication Setup

Insert this as a subsection immediately after the mcps/trello.py code block in Section 9.
Replace the existing one-liner: "Trello API key and token are obtained from https://trello.com/app-key"

Trello authentication uses a static API key and token pair. These do not expire
and do not require a refresh flow. Both are obtained from Trello's developer portal
in under two minutes.

**Step 1** — Get your API Key
1. Log in to Trello at https://trello.com
2. Navigate to https://trello.com/app-key
3. Copy the API Key shown at the top of the page.
This is your TRELLO_API_KEY.

```
Note: If you see a warning about enabling Power-Ups, dismiss it.
The API key is available regardless of Power-Up status.
```

**Step 2** — Generate a Token
On the same page (https://trello.com/app-key), click the "Token" link
in the paragraph below your API key. It reads:

"You can also manually generate a Token."


A Trello authorization page opens. Click "Allow".
Copy the long token string shown on the confirmation page.
This is your `TRELLO_TOKEN`.

```
Note: This token grants full read/write access to your Trello account.
It does not expire unless you revoke it manually from
https://trello.com/your-username/account (under "Applications").
```

**Step 3** — Add to .env
```dotenv
TRELLO_API_KEY=your_40_character_api_key_here
TRELLO_TOKEN=your_64_character_token_here
```

**Step 4** — Verify
Test that the MCP server starts and can reach Trello:
```powershell
# Set env vars temporarily and run the MCP server directly
$env:TRELLO_API_KEY="your_key"
$env:TRELLO_TOKEN="your_token"
npx -y @modelcontextprotocol/server-trello
```
If Node.js is not installed, the npx command will fail. Install Node.js from
https://nodejs.org (LTS version). The Trello MCP server is an npm package —
Node.js is a hard dependency.

Expected output: the process starts and waits on stdin. Press Ctrl+C to exit.
No error output means authentication is valid.

### 9B. Google Workspace Authentication Setup (Stage 2C — Manual Token)

Google's remote MCP endpoints for Gmail and Calendar require an OAuth 2.0
bearer token in the Authorization header. In Stage 2C this token is set
manually as an environment variable. It expires after 1 hour.

Stage 3b will replace this with an automatic token refresh flow. For Stage 2C,
regenerate the token when you get a 401 from the Google remote MCP.

The existing GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET from
prior stages are reused here — no new OAuth app registration is needed.

**Prerequisites — Enable APIs in Google Cloud Console**
If not already done from a prior stage:

1. Go to https://console.cloud.google.com
2. Select your project (GOOGLE_CLOUD_PROJECT)
3. Navigate to APIs & Services → Library
4. Search for and Enable both:
   - Gmail API
   - Google Calendar API

``
If these were enabled in a prior stage for workspace-mcp, they are already
enabled. Skip to Step 1.
``

**Step 1** — Confirm OAuth Consent Screen
1. In Google Cloud Console → APIs & Services → OAuth consent screen
2. If not configured: choose External, fill in App name and your email,
save. No further configuration needed for personal use.
3. Under Scopes, confirm these scopes are added (add if missing):
   - https://www.googleapis.com/auth/gmail.modify
   - https://www.googleapis.com/auth/calendar

**Step 2** — Confirm OAuth 2.0 Credentials Exist
1. In Google Cloud Console → APIs & Services → Credentials
2. You should already have an OAuth 2.0 Client ID of type Desktop app
from a prior stage. If so, skip to Step 3.
3. If not: click Create Credentials → OAuth client ID → Desktop app.
Name it anything (e.g. personal-assistant-dev). Download the JSON — you
won't need the file directly, but note the Client ID and Secret.
4. Confirm GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET in .env
match this credential.

**Step 3** — Generate an Access Token via OAuth Playground
The OAuth Playground at https://developers.google.com/oauthplayground lets you
generate a bearer token without writing any code.

Open https://developers.google.com/oauthplayground in your browser.
Click the gear icon (⚙) in the top-right corner.
1. Check "Use your own OAuth credentials".
2. Enter your GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.
Close the settings panel.
3. In the left panel under "Step 1 — Select & authorize APIs":
Paste each scope on its own line in the input box at the bottom:

```
   https://www.googleapis.com/auth/gmail.modify
   https://www.googleapis.com/auth/calendar
```

**Click "Authorize APIs".**

4. A Google sign-in page opens. Sign in with the Google account that owns
the Gmail and Calendar you want the assistant to access.
5. Click "Allow" on the consent screen.
You are returned to the Playground. In "Step 2 — Exchange authorization
code for tokens", click "Exchange authorization code for tokens".
6. The Access token field is populated with a ya29.xxx string.
Copy it. This is your GOOGLE_ACCESS_TOKEN.

```
Token lifetime: 1 hour from the moment you clicked "Exchange".
When it expires, the Google remote MCP returns HTTP 401.
Repeat from Step 3 (you do not need to re-authorize scopes — just click
"Exchange authorization code for tokens" again with a new auth code).
```

**Step 4** — Add to .env

```dotenv
GOOGLE_ACCESS_TOKEN=ya29.your_access_token_here
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
```
`GOOGLE_CLOUD_PROJECT` is the Project ID (not the project name) shown in
the Google Cloud Console dashboard header, e.g. my-assistant-123456.

**Step 5** — Verify
Test that the Gmail endpoint is reachable with your token:
```powershell
# Windows PowerShell
$token = "ya29.your_token_here"
Invoke-RestMethod `
  -Uri "https://gmail.googleapis.com/gmail/v1/users/me/profile" `
  -Headers @{ Authorization = "Bearer $token" }
```
```bash
# macOS / Linux
curl -H "Authorization: Bearer ya29.your_token_here" \
  https://gmail.googleapis.com/gmail/v1/users/me/profile
```

Expected response: a JSON object containing `emailAddress`, `messagesTotal`,
and `threadsTotal`. Any 401 means the token is expired or the wrong account
was used. Any 403 means the Gmail API is not enabled in your project.

**Token Expiry During Development**

When the token expires mid-session, the Google remote MCP returns 401 and
the specialist agent will fail with a tool error. The troubleshooting entry in
Section 14 covers this. 

The fix for Stage 2C is manual regeneration:
1. Return to https://developers.google.com/oauthplayground
2. Click "Exchange authorization code for tokens" again
3. Copy the new ya29.xxx token
4. Update GOOGLE_ACCESS_TOKEN in .env
5. Restart the FastAPI process (uvicorn gateway.app:app --reload will pick
up the new env var automatically if using --reload)

Stage 3b will introduce a token cache with automatic refresh so this manual
step is no longer needed.

---

## 10. `memory/sqlite_store.py` — Reminders DDL

Add to `initialise()` after the `agent_turns` DDL:

```python
await db.execute("""
    CREATE TABLE IF NOT EXISTS reminders (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        text       TEXT    NOT NULL,
        remind_at  TEXT    NOT NULL,
        created_at TEXT    NOT NULL,
        fired      INTEGER NOT NULL DEFAULT 0
    )
""")
await db.commit()
```

The `fired` column is 0 for all Stage 2C operations. A future stage uses it to
track which reminders have already been sent proactively. Adding it now avoids
a schema migration later.

---

## 11. `agents/reminders.py` — Full Implementation

`RemindersAgent` is a custom agent with no MCP connection. Its tools are Python
functions operating directly on SQLite. It uses the same `.run(sub_task, deps)`
interface as `SpecialistAgent` so the supervisor calls it identically.

The registry constructs it via dynamic import — `agent_class: "RemindersAgent"`
and `module_path: "agents.reminders"` in the SKILL.md frontmatter. No hardcoding
in `registry.py` is needed or permitted.

### Pydantic schema

```python
# schemas/reminder.py
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

### Tool functions — `tools/reminder_tools.py`

```python
import os
from datetime import datetime, timezone
import aiosqlite
from schemas.reminder import Reminder

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

### `agents/reminders.py`

```python
from __future__ import annotations

import os
from datetime import date

from pydantic_ai import Agent

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from schemas.agent_registration import AgentRegistration
from schemas.specialist_result import SpecialistResult
from tools.reminder_tools import create_reminder, list_reminders, delete_reminder

_factory = LLMFactory()


class RemindersAgent(BaseAgent):
    """
    Custom specialist agent for personal reminder management.
    Tools are Python functions operating on SQLite — no MCP connection.
    Uses the same .run(sub_task, deps) interface as SpecialistAgent.
    Constructed by the registry via dynamic import from SKILL.md.
    """

    def __init__(self, key: str, registration: AgentRegistration, user_email: str = None) -> None:
        super().__init__(name=key)
        self._key = key
        self._registration = registration

        self._agent = Agent(
            model=_factory.get_model(os.getenv("SPECIALIST_MODEL")),
            system_prompt=self._build_system_prompt(registration),
            output_type=SpecialistResult,
            deps_type=AgentDeps,
            tools=[create_reminder, list_reminders, delete_reminder],
        )

    def _build_system_prompt(self, reg: AgentRegistration) -> str:
        today = date.today().isoformat()
        return f"""
            Today's date is {today}.

            [IDENTITY]
            {reg.system_instructions}

            [GLOBAL OPERATIONAL RULES]
            1. Domain Integrity: Your scope is strictly limited to: {reg.owns}.
            2. Validation First: BEFORE calling any tool, verify you have all required information.
            3. Missing Information: If any required parameter is missing, DO NOT call any tools.
               Populate 'missing_info' with what is needed and return immediately.
            4. Execution: Only call tools if you have 100% of the required parameters.
            5. Output: Log one actions_taken entry per tool call. Provide a concise summary.
        """

    async def run(self, sub_task: str, deps: AgentDeps) -> SpecialistResult:
        logger.warning(
            "RemindersAgent[%s].run | user=%s | sub_task=%r",
            self._key, deps.user_id, sub_task,
        )
        result = await self._agent.run(user_prompt=sub_task, deps=deps)
        output: SpecialistResult = result.output
        logger.warning(
            "RemindersAgent[%s].result | user=%s | actions=%r | missing=%r",
            self._key, deps.user_id, output.actions_taken, output.missing_info,
        )
        return output
```

---

## 12. `agents/personal_notes.py` — Full Implementation

`PersonalNoteAgent` is a custom agent that saves freeform text to local `.txt`
files. No MCP connection. Its tool is a single Python function `save_as_txt`.
Constructed by the registry via dynamic import from SKILL.md.

### Tool function — `tools/personal_notes_tools.py`

```python
import os
from datetime import date
from pydantic_ai import RunContext
from core.deps import AgentDeps

_NOTES_DIR = os.getenv("NOTES_DIR", "data/notes")


async def save_as_txt(ctx: RunContext[AgentDeps], filename: str, content: str) -> str:
    """Save content to a .txt file in the notes directory.

    Args:
        filename: the file name including .txt extension
        content:  the full text content to write

    Returns:
        str: confirmation message with filename and character count
    """
    os.makedirs(_NOTES_DIR, exist_ok=True)

    if not filename.endswith(".txt"):
        filename = filename + ".txt"

    filepath = os.path.join(_NOTES_DIR, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return f"Saved '{filename}' ({len(content)} characters) to {filepath}"
```

Add to `.env`:
```
NOTES_DIR=data/notes
```

### `agents/personal_notes.py`

```python
from __future__ import annotations

import os
from datetime import date

from pydantic_ai import Agent

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger
from schemas.agent_registration import AgentRegistration
from schemas.specialist_result import SpecialistResult
from tools.personal_notes_tools import save_as_txt

_factory = LLMFactory()


class PersonalNoteAgent(BaseAgent):
    """
    Custom specialist agent for saving personal notes to local .txt files.
    No MCP connection. Single tool: save_as_txt.
    Constructed by the registry via dynamic import from SKILL.md.
    """

    def __init__(self, key: str, registration: AgentRegistration, user_email: str = None) -> None:
        super().__init__(name=key)
        self._key = key
        self._registration = registration

        self._agent = Agent(
            model=_factory.get_model(os.getenv("SPECIALIST_MODEL")),
            system_prompt=self._build_system_prompt(registration),
            output_type=SpecialistResult,
            deps_type=AgentDeps,
            tools=[save_as_txt],
        )

    def _build_system_prompt(self, reg: AgentRegistration) -> str:
        today = date.today().isoformat()
        return f"""
            Today's date is {today}.

            [IDENTITY]
            {reg.system_instructions}

            [GLOBAL OPERATIONAL RULES]
            1. Domain Integrity: Your scope is strictly limited to: {reg.owns}.
            2. Validation First: The note 'content' is mandatory. If it is missing, DO NOT call save_as_txt.
            3. Missing Information: If content is absent, populate 'missing_info' with what is needed
               and return immediately. Do not call any tools.
            4. Filename: If the user specifies a filename use it exactly. If not, generate one using
               lowercase words and underscores with today's date suffix: topic_2026-06-02.txt
            5. Output: After save_as_txt completes, populate actions_taken with one entry describing
               what was saved and to which file. Set missing_info to null.
        """

    async def run(self, sub_task: str, deps: AgentDeps) -> SpecialistResult:
        logger.warning(
            "PersonalNoteAgent[%s].run | user=%s | sub_task=%r",
            self._key, deps.user_id, sub_task,
        )
        result = await self._agent.run(user_prompt=sub_task, deps=deps)
        output: SpecialistResult = result.output
        logger.warning(
            "PersonalNoteAgent[%s].result | user=%s | actions=%r | missing=%r",
            self._key, deps.user_id, output.actions_taken, output.missing_info,
        )
        return output
```

### How the registry constructs these agents

Both agents follow the same registry path as every other specialist. No special
casing in `registry.py`. The SKILL.md frontmatter fields `agent_class` and
`module_path` drive construction:

```
skills/reminders/SKILL.md
  agent_class: "RemindersAgent"
  module_path:  "agents.reminders"
  → importlib.import_module("agents.reminders")
  → getattr(module, "RemindersAgent")
  → RemindersAgent(key="reminders", registration=..., user_email=...)

skills/personal_notes/SKILL.md
  agent_class: "PersonalNoteAgent"
  module_path:  "agents.personal_notes"
  → importlib.import_module("agents.personal_notes")
  → getattr(module, "PersonalNoteAgent")
  → PersonalNoteAgent(key="personal_notes", registration=..., user_email=...)
```

`get_pool_server()` returns `None` for both because `server_type: "none"`.
Neither agent passes through `SpecialistAgent` — they are constructed directly
from their own classes. The `toolsets=[]` path in `SpecialistAgent` is irrelevant
here because these agents are not `SpecialistAgent` instances at all.

---

## 13. File Layout After Stage 2C

```
project/
├── agents/
│   ├── base.py
│   ├── personal_notes.py       NEW
│   ├── reminders.py            NEW
│   ├── specialist.py           unchanged
│   └── supervisor.py           UPDATED (run() signature and return type)
├── core/
│   ├── deps.py
│   ├── llm_factory.py
│   ├── logger.py
│   └── registry.py             unchanged
├── gateway/
│   ├── app.py                  UPDATED (history lists, _process, /assistant)
│   └── telegram_client.py
├── mcps/
│   ├── google.py               unchanged (kept for reference, no longer used)
│   ├── google_remote.py        NEW
│   ├── mcp_pool.py             UPDATED (server_type routing)
│   └── trello.py               NEW
├── memory/
│   ├── sqlite_store.py         UPDATED (reminders DDL)
│   └── ...
├── schemas/
│   ├── agent_registration.py   unchanged (server_type field already present)
│   ├── reminder.py             NEW
│   ├── specialist_result.py
│   ├── supervisor_response.py
│   └── turn_record.py
├── skills/
│   ├── calendar/
│   │   └── SKILL.md            UPDATED (server_type: google_remote)
│   ├── email/  →  gmail/
│   │   └── SKILL.md            UPDATED (key, server_type: google_remote)
│   ├── personal_notes/
│   │   └── SKILL.md            NEW
│   ├── reminders/
│   │   └── SKILL.md            NEW
│   ├── tasks/
│   │   └── SKILL.md            DELETED
│   └── trello/
│       └── SKILL.md            NEW
├── tools/
│   ├── personal_notes_tools.py NEW
│   └── reminder_tools.py       NEW
├── main.py
└── .env                        UPDATED (new env vars)
```

---

## 12. Environment Variables

Full `.env` after Stage 2C:

```dotenv
# Telegram
WEBHOOK_SECRET=your_webhook_secret
TELEGRAM_CHAT_ID=your_chat_id

# Identity
USER_ID=local_user
USER_GOOGLE_EMAIL=your@gmail.com

# Models
SUPERVISOR_MODEL=claude-opus-4-6
SPECIALIST_MODEL=claude-sonnet-4-6

# Google OAuth (existing)
GOOGLE_OAUTH_CLIENT_ID=your_client_id
GOOGLE_OAUTH_CLIENT_SECRET=your_client_secret
OAUTHLIB_INSECURE_TRANSPORT=1

# Google Remote MCP (NEW)
GOOGLE_ACCESS_TOKEN=ya29.your_access_token
GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# Trello (NEW)
TRELLO_API_KEY=your_trello_api_key
TRELLO_TOKEN=your_trello_token

# Storage
SQLITE_PATH=data/assistant.db
```

---

## 13. Implementation Order

### Phase 1 — Conversation History

1. Update `SupervisorAgent.run()` signature and return type in `agents/supervisor.py`.
2. Add `_message_history` and `_assistant_history` to `gateway/app.py`.
3. Update `_process()` to unpack the tuple and store history.
4. Update `/assistant` endpoint to unpack the tuple and store history.
5. Smoke test via `/assistant`:

| Turn | Input | Expected |
|---|---|---|
| 1 | `any pending tasks in trello?` | Lists cards from the default board |
| 2 | `when is the first one due?` | Supervisor uses context from turn 1, returns due date |
| 3 | `mark it complete` | Specialist resolves "it" from history, marks the card |

Verify in logs that turn 2's `SupervisorAgent.run` log shows the history being
passed and the supervisor correctly references the card from turn 1.

### Phase 2 — Trello Integration

1. Create `mcps/trello.py` from Section 9.
2. Create `skills/trello/SKILL.md` from Section 4.
3. Update `mcps/mcp_pool.py` from Section 7.
4. Add `TRELLO_API_KEY` and `TRELLO_TOKEN` to `.env`.
5. Test:

| Input | Expected |
|---|---|
| `what boards do I have in trello?` | Lists board names |
| `show me the cards in my To Do list on the Work board` | Lists cards |
| `add a card called Fix login bug to the To Do list on Work board` | Card created, confirmation |
| `move Fix login bug to In Progress` | Card moved, confirmation |

### Phase 3 — Google Remote MCP (Gmail + Calendar)

1. Create `mcps/google_remote.py` from Section 8.
2. Update `skills/gmail/SKILL.md` with `server_type: "google_remote"`.
3. Update `skills/calendar/SKILL.md` with `server_type: "google_remote"`.
4. Rename `skills/email/` to `skills/gmail/` and update the key.
5. Add `GOOGLE_ACCESS_TOKEN` and `GOOGLE_CLOUD_PROJECT` to `.env`.
6. Test:

| Input | Expected |
|---|---|
| `search my gmail for emails from John` | Returns matching emails |
| `draft an email to john@example.com subject Hello body Just checking in` | Draft created |
| `what's on my calendar tomorrow?` | Lists events for tomorrow MYT |
| `schedule a meeting called Budget Review for Friday 3pm` | Event created |

### Phase 4 — Personal Notes Registration

1. Create `skills/personal_notes/SKILL.md` from Section 4.
2. Remove any hardcoded `if key == "personal_notes"` branch from `registry.py`
   `build_specialist()` if it exists.
3. Restart and confirm startup log:

```
registry | compiled skill configuration target: personal_notes
```

4. Test:

| Input | Expected |
|---|---|
| `save a note: remember to buy milk` | File saved, filename and path confirmed |
| `save this as shopping.txt: eggs, bread, coffee` | File saved as shopping.txt |
| `save a note` | missing_info returned, no file created |

### Phase 5 — Delete Tasks Skill

1. Delete `skills/tasks/SKILL.md`.
2. Restart and confirm `tasks` no longer appears in startup logs.
3. Test that `any tasks?` or similar is now either routed to Trello or answered
   conversationally with a clarification.

### Phase 6 — Full Integration Test

```powershell
uvicorn gateway.app:app --reload
```

Expected startup logs:
```
registry | compiled skill configuration target: gmail
registry | compiled skill configuration target: calendar
registry | compiled skill configuration target: trello
registry | compiled skill configuration target: personal_notes
registry | compiled skill configuration target: reminders
gateway | started | user=local_user | email=...
```

Full multi-turn Telegram smoke test:

| Turn | Message | Expected |
|---|---|---|
| 1 | `What can you help me with?` | Conversational reply listing capabilities |
| 2 | `show me my trello boards` | Lists boards |
| 3 | `add a card called Review spec to the first board` | Card created |
| 4 | `when is it due?` | Supervisor uses history, reports due date (or none set) |
| 5 | `what's on my calendar today?` | Calendar events for today MYT |
| 6 | `search gmail for invoices` | Returns matching emails |
| 7 | `save a note: follow up on invoice from last week` | File saved, path confirmed |
| 8 | `remind me to check that note tomorrow at 9am` | Reminder stored |
| 9 | `what reminders do I have?` | Lists the reminder |
| 10 | `/start` | `Assistant ready. Send me a message.` |

---

## 14. Troubleshooting

**History not working — follow-up questions fail**

Confirm `SupervisorAgent.run()` returns a tuple and all callers unpack it.
Check that `_message_history` is declared `global` inside `_process()` and
`_assistant_history` is declared `global` inside the `/assistant` handler.
Add a debug log: `logger.warning("history length: %d", len(_message_history))`
before the `_supervisor.run()` call to confirm history is accumulating.

**`personal_notes` not in startup logs**

Confirm `skills/personal_notes/SKILL.md` exists and starts with `---` on the
first line. Confirm `agent_class: "PersonalNoteAgent"` and
`module_path: "agents.personal_notes"` are in the frontmatter. Check for a
`registry | structural parse failure` log line.

**`personal_notes` agent raises `ImportError`**

The `module_path` in the SKILL.md must match the actual Python module path
exactly. Confirm `agents/personal_notes.py` exists and the class inside is
named `PersonalNoteAgent`.

**Trello MCP server fails to start**

Confirm `npx` is available in the PATH inside the container/venv. The Trello
MCP server is an npm package — Node.js must be installed. Check `TRELLO_API_KEY`
and `TRELLO_TOKEN` are set and valid. Test manually:
```powershell
npx -y @modelcontextprotocol/server-trello
```

**Google remote MCP returns 401**

`GOOGLE_ACCESS_TOKEN` has expired. Google OAuth access tokens expire after 1
hour. Refresh manually for Stage 2C. Stage 3b introduces token refresh. Confirm
`GOOGLE_CLOUD_PROJECT` matches the project where Workspace APIs are enabled.

**Two history lists causing confusion during testing**

`/assistant` uses `_assistant_history`. Telegram uses `_message_history`. They
are intentionally separate. If you want to reset one without restarting, add a
debug endpoint:
```python
@app.post("/debug/reset-history")
async def reset_history() -> dict:
    global _message_history, _assistant_history
    _message_history = []
    _assistant_history = []
    return {"ok": True}
```

**`tasks` key still being routed**

Confirm `skills/tasks/SKILL.md` is deleted and the process has been restarted.
The registry is populated at startup from disk — a running process will not
reflect file deletions until restart.

---

## 15. How Stage 3b Builds on This

Stage 2C establishes in-memory conversation history scoped to the FastAPI process
lifetime. Nothing in Stage 2C changes in Stage 3b.

Stage 3b introduces persistence and enrichment:

- **History persistence** — `SQLiteStore.get_history()` returns `ModelMessage`
  objects (not raw dicts). The history list passed to `_supervisor.run()` comes
  from the database instead of the module-level list. The module-level lists are
  removed.
- **User context file** — `memory/brain/user.md` is loaded at startup and
  injected into every specialist's system prompt. Contains timezone, contact
  shortcuts, preferences.
- **Token management** — Google OAuth token refresh logic added to
  `mcps/google_remote.py`. `GOOGLE_ACCESS_TOKEN` env var replaced by a token
  cache with automatic refresh.

The registry, `mcp_pool`, `SpecialistAgent`, `PersonalNoteAgent`, and the
Telegram webhook flow do not change in Stage 3b.

---

## 16. Done When

- App starts and logs exactly five skill configuration targets: `gmail`,
  `calendar`, `trello`, `personal_notes`, `reminders`
- `tasks` does not appear in startup logs
- Follow-up questions resolve correctly across at least three consecutive turns
  via both `/assistant` and Telegram webhook
- `/assistant` history and Telegram history are independent — a test via
  `/assistant` does not affect the Telegram conversation
- Trello boards, lists, and cards are readable and writable via Telegram
- Gmail search and draft creation work via Telegram
- Calendar event listing and creation work via Telegram, times shown in MYT
- `personal_notes` agent is discovered via registry (log confirms), not hardcoded
- Personal note saving works via Telegram
- All Stage 3a smoke tests pass unchanged (reminders create/list/delete)
- `docker compose up -d --build` produces a working container with correct startup
  log sequence