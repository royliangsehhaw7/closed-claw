# Personal Telegram Assistant
## Specification — Stage 1a: Skeleton + Simple Chat Agent

> **Assumes:** Pre-setup complete — Python environment active, `.env` file present,
> Google credentials exist, Telegram bot token obtained, Docker with Redis container
> available (not required yet this stage).
>
> **Branch:** `stage/1a` branched from `main`
>
> **Done when:** `python main.py` accepts typed input, Supervisor responds, response
> is printed to terminal and written to `logs/assistant.log`. All schemas import without
> error. No Telegram, no MCP, no Redis this stage.

---

## 1. Purpose

Build the complete foundational layer of the assistant. Every file created in this stage
is imported by every subsequent stage. The goal is a stable, tested skeleton — correct
structure, correct types, correct logging — before any integration complexity enters.

The simple chat agent at the end of this stage is not a throwaway. It is the first real
proof that `logging → schemas → deps → llm_factory → blackboard → base agent → supervisor`
all wire together correctly.

---

## 2. Project Structure

```
project/
├── agents/
│   ├── __init__.py
│   ├── base_agent.py                  # BaseAgent ABC — all agents inherit this
│   └── supervisor.py            # Supervisor agent — entry point for all requests
│
├── core/
│   ├── __init__.py
│   ├── logger.py                # Logging setup — FileHandler + StreamHandler
│   ├── deps.py                  # AgentDeps — typed dependency container
│   ├── llm_factory.py           # Centralised LLM instantiation
│   └── blackboard.py            # Shared agent state, in-memory for now
│
├── schemas/
│   ├── __init__.py              # Re-exports all models for clean imports
│   ├── message.py               # Message — normalised inbound message
│   ├── agent_task.py            # AgentTask — unit of work for the queue
│   ├── turn_record.py           # TurnRecord — SQLite turn log entry
│   ├── task_item.py             # TaskItem — Google Task representation
│   ├── calendar_event.py        # CalendarEvent — Google Calendar event
│   └── session_history.py       # SessionMessage + SessionHistory
│
├── memory/
│   ├── agents/
│   │   └── supervisor.md        # Supervisor system prompt / persona
│   └── brain/
│       └── user.md              # User facts (empty template for now)
│
├── logs/                        # Created at runtime, never committed
├── main.py                      # Entry point: python main.py
├── .env                         # Never committed
├── .env.example                 # Committed — shows required keys, no values
├── .gitignore
└── requirements.txt
```

---

## 3. Architecture — Stage 1a

```
stdin (terminal)
   │  raw text input
   ▼
main.py
   · initialises logger
   · builds AgentDeps
   · calls supervisor.run(user_input, deps)
   │
   ▼
SupervisorAgent
   · loads persona from memory/agents/supervisor.md
   · calls LLM via LLMFactory
   · returns plain text response
   │
   ▼
main.py
   · prints response to stdout
   · logger records the exchange
```

No delegation to specialist agents this stage. No tools. No MCP. The Supervisor is the
only agent and it responds directly.

---

## 4. .env.example

```
# LLM Provider
LLM_ORGANIZATION=gemini
LLM_MODEL=gemini-2.0-flash

# API Keys
GEMINI_API_KEY=
OPENROUTER_API_KEY=

# Telegram (not used until Stage 2)
TELEGRAM_BOT_TOKEN=

# Paths
LOG_FILE=logs/assistant.log
LOG_LEVEL=INFO
MEMORY_DIR=memory/

# Database (not used until Stage 3)
REDIS_URL=redis://localhost:6379
SQLITE_PATH=data/assistant.db
```

---

## 5. core/logger.py

Follows your existing `logger.py` pattern. Writes to both file and console.
All modules import `logger` from here: `from core.logger import logger`.

```python
import sys
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

log_file = os.getenv("LOG_FILE", "logs/assistant.log")
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

Path(log_file).parent.mkdir(parents=True, exist_ok=True)

fmt = "%(asctime)s [%(levelname)s] %(name)s | %(message)s"

logging.basicConfig(
    level=log_level,
    format=fmt,
    handlers=[
        RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("app")
```

---

## 6. schemas/message.py

```python
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


# Purpose: Normalised inbound message from any channel.
# Every message entering the system — whether from Telegram, CLI, or the
# Heartbeat engine — is converted into this shape before anything else touches it.
# The Gateway (Stage 2) is responsible for the conversion. Agents never see
# raw Telegram Update objects; they only ever see a Message.
# Channel field distinguishes the source for logging and routing purposes.
class Message(BaseModel):
    message_id: str
    user_id: str
    text: str
    channel: str = "cli"           # "cli" | "telegram"
    timestamp: datetime = Field(default_factory=datetime.now)
```

---

## 7. schemas/agent_task.py

```python
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field

from schemas.message import Message


# Purpose: Unit of work placed on the per-user asyncio.Queue (Stage 2).
# The Gateway wraps every inbound Message in an AgentTask before enqueuing it.
# The Heartbeat engine (Stage 3) also produces AgentTasks — with source="heartbeat" —
# so the agent loop treats deadline alerts identically to user messages.
# The drain coroutine dequeues one AgentTask at a time per user, ensuring
# messages are processed in order with no concurrency per user.
class AgentTask(BaseModel):
    task_id: str
    user_id: str
    message: Message
    source: str = "user"           # "user" | "heartbeat"
    created_at: datetime = Field(default_factory=datetime.now)
```

---

## 8. schemas/turn_record.py

```python
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


# Purpose: One agent exchange written to the SQLite agent_turns table (Stage 1c).
# Written after every Supervisor run — captures input, output, which agent
# handled it, which model was used, and token counts for cost tracking.
# Append-only. Never updated after writing. Queryable for debugging and
# reviewing conversation history without relying on Redis.
class TurnRecord(BaseModel):
    turn_id: str
    user_id: str
    agent_name: str
    user_input: str
    agent_output: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)
```

---

## 9. schemas/task_item.py

```python
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


# Purpose: Internal representation of a Google Task.
# The Concierge agent (Stage 1c) maps raw Google Tasks API responses into
# this shape before working with them or returning them to the user.
# list_id and list_name together support the Kanban-style movement of tasks
# between lists without a separate lookup. The status field mirrors the
# Google Tasks API values exactly to avoid translation errors.
class TaskItem(BaseModel):
    task_id: str
    title: str
    list_id: str
    list_name: str
    due: datetime | None = None
    status: str = "needsAction"    # "needsAction" | "completed"
    notes: str | None = None
```

---

## 10. schemas/calendar_event.py

```python
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel


# Purpose: Internal representation of a Google Calendar event.
# Every task deadline is reflected as a CalendarEvent — the Concierge agent
# creates or updates one whenever a task is created or its deadline changes.
# task_id links the event back to its originating TaskItem so the two stay
# in sync. The Heartbeat engine (Stage 3) reads CalendarEvents to determine
# which deadlines are approaching and need a Telegram alert.
class CalendarEvent(BaseModel):
    event_id: str
    title: str
    start: datetime
    end: datetime
    description: str | None = None
    task_id: str | None = None     # links back to the originating TaskItem
```

---

## 11. schemas/session_history.py

```python
from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


# Purpose: Wraps the Redis message list for a single user (Stage 3).
# SessionMessage is one turn — role is either "user" or "assistant".
# SessionHistory holds the ordered list of SessionMessages for a user
# and is loaded from Redis at the start of each request, injected into
# AgentDeps, and passed as message_history to the agent so it has
# conversational context across separate Telegram messages.
# TTL is managed by Redis directly — no expiry logic needed here.
class SessionMessage(BaseModel):
    role: str                      # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)


class SessionHistory(BaseModel):
    user_id: str
    messages: list[SessionMessage] = Field(default_factory=list)
```

---

## 12. schemas/\_\_init\_\_.py

Re-exports all models so imports across the project stay clean.

```python
from schemas.message import Message
from schemas.agent_task import AgentTask
from schemas.turn_record import TurnRecord
from schemas.task_item import TaskItem
from schemas.calendar_event import CalendarEvent
from schemas.session_history import SessionMessage, SessionHistory

__all__ = [
    "Message",
    "AgentTask",
    "TurnRecord",
    "TaskItem",
    "CalendarEvent",
    "SessionMessage",
    "SessionHistory",
]
```

---

## 13. core/deps.py

Typed dependency container injected into every agent's `RunContext`. Fields requiring
Redis or SQLite are stubbed with `None` and wired in Stage 3.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentDeps:
    user_id: str
    session_history: list[dict[str, str]] = field(default_factory=list)

    # Wired in Stage 3
    redis_client: Any | None = None
    sqlite_conn: Any | None = None

    # Shared state across agents in a single request
    blackboard: Any | None = None
```

---

## 14. core/llm_factory.py

Reads config from `.env` via `os.getenv`. No settings class needed.

```python
from __future__ import annotations

import os
from dotenv import load_dotenv

from pydantic_ai.models.google import GoogleModel, GoogleModelSettings
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from core.logger import logger

load_dotenv()


class LLMFactory:
    def __init__(self, organization: str | None = None):
        self._organization = organization or os.getenv("LLM_ORGANIZATION", "gemini")

    def get_model(self, model: str | None = None):
        name = model or os.getenv("LLM_MODEL", "gemini-2.0-flash")
        logger.debug("LLMFactory | org=%s model=%s", self._organization, name)

        if self._organization == "gemini":
            return self._get_google_model(name)
        return self._get_openrouter_model(name)

    # -- private

    def _get_google_model(self, name: str) -> GoogleModel:
        return GoogleModel(
            model_name=name,
            provider=GoogleProvider(api_key=os.getenv("GEMINI_API_KEY")),
            settings=GoogleModelSettings(temperature=0.15),
        )

    def _get_openrouter_model(self, name: str) -> OpenRouterModel:
        return OpenRouterModel(
            model_name=name,
            provider=OpenRouterProvider(
                api_key=os.getenv("OPENROUTER_API_KEY"),
                app_url="https://openrouter.ai/api/v1",
            ),
            settings=OpenRouterModelSettings(
                tool_choice="auto",
                temperature=0.15,
            ),
        )
```

---

## 15. core/blackboard.py

In-memory shared state store for this stage. Stage 3 adds Redis backing without
changing the public interface.

```python
from __future__ import annotations

from typing import Any

from core.logger import logger


class Blackboard:
    """Shared state store for a single request lifecycle.

    Agents write findings here; downstream agents read them.
    Backing store is in-memory for Stage 1a.
    Stage 3 adds Redis backing without changing the public interface.
    """

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    def write(self, key: str, value: Any) -> None:
        logger.debug("Blackboard.write | key=%s", key)
        self._store[key] = value

    def read(self, key: str, default: Any = None) -> Any:
        return self._store.get(key, default)

    def clear(self) -> None:
        self._store.clear()

    def snapshot(self) -> dict[str, Any]:
        return dict(self._store)
```

---

## 16. agents/base.py

```python
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic_ai import Agent
from core.logger import logger

class BaseAgent(ABC):
    """All agents inherit from this class.

    Responsibilities:
    - Loads its persona from memory/agents/<name>.md at construction time.
    - Wraps pydantic-ai Agent.
    - Enforces a consistent run() interface across all agents.
    """

    def __init__(self, name: str) -> None:   # agent no longer passed in here
        self._name = name
        self._persona = self._load_persona()  # safe — self._name exists
        self._agent: Agent | None = None      # set by subclass after super().__init__
        logger.debug("BaseAgent | %s initialised", self._name)
        
    @property
    def name(self) -> str:
        return self._name

    def _load_persona(self) -> str:
        """Load system prompt from memory/agents/<name>.md.

        Returns empty string if the file does not exist — agent falls
        back to its hardcoded instruction string.
        """
        memory_dir = os.getenv("MEMORY_DIR", "memory/")
        path = Path(memory_dir) / "agents" / f"{self._name}.md"
        if path.exists():
            content = path.read_text(encoding="utf-8")
            logger.debug("BaseAgent | persona loaded from %s", path)
            return content
        logger.warning("BaseAgent | no persona file found at %s", path)
        return ""

    @abstractmethod
    async def run(self, user_input: str, deps: object) -> str:
        """Run the agent and return a plain text response."""
        ...

```

---

## 17. agents/supervisor.py

```python
from __future__ import annotations

from pydantic_ai import Agent

from agents.base import BaseAgent
from core.deps import AgentDeps
from core.llm_factory import LLMFactory
from core.logger import logger

_factory = LLMFactory()

class SupervisorAgent(BaseAgent):
    """Entry point for all user requests.

    Stage 1a: responds directly, no delegation.
    Stage 1c: classifies intent and delegates to Concierge or Comms.
    """

    def __init__(self) -> None:
        # Build the agent AFTER super().__init__ so self._persona is available
        super().__init__(name="supervisor")          # persona loaded here
        agent = Agent(
            model=_factory.get_model(),
            system_prompt=self._build_system_prompt(),  # safe to call now
        )
        self._agent = agent
        self._history = []


    def _build_system_prompt(self) -> str:
        base = (f"""
                You are a personal assistant.
                You help the user manage their tasks, calendar, and email.
                Be concise and helpful.
            """
        )
        return f"{base}\n\n{self._persona}".strip() if self._persona else base

    async def run(self, user_input: str, deps: AgentDeps) -> str:
        logger.info("SupervisorAgent.run | user=%s | input=%r", deps.user_id, user_input)

        result = await self._agent.run(
            user_prompt=user_input,
            deps=deps,
            message_history=self._history
        )
        # 2. Update your local history with the NEW messages
        # result.new_messages contains only the messages added in this turn
        self._history = result.all_messages()
        
        response = result.output
        logger.info(f"""
            SupervisorAgent.run | response= {response}
            Thinking : {str(result.response.thinking).strip()}
        """)

        return response
```

---

## 18. memory/agents/supervisor.md

```markdown
# Supervisor

You are a calm, efficient personal assistant. You speak in plain, direct sentences.
You do not use bullet points unless the user asks for a list.
You never make up information about the user's tasks or calendar.
When you do not know something, you say so plainly and ask a clarifying question.
```

---

## 19. memory/brain/user.md

```markdown
# User

Name: (not yet provided)
Timezone: (not yet provided)
Preferences: (not yet provided)
```

---

## 20. main.py

```python
"""Entry point for Stage 1a.

Run with:
    python main.py

Replaced by the FastAPI Gateway entry point in Stage 2. The agent loop
logic here mirrors what will run inside the per-user asyncio.Queue drain
coroutine in Stage 2 — kept intentionally simple.
"""

from __future__ import annotations

import asyncio

from core.logger import logger
from core.deps import AgentDeps
from core.blackboard import Blackboard
from agents.supervisor import SupervisorAgent

USER_ID = "local_user"


async def main() -> None:
    supervisor = SupervisorAgent()

    logger.info("Assistant started | user=%s", USER_ID)
    print("Assistant ready. Type your message. Ctrl+C to exit.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye.")
            logger.info("Assistant stopped by user")
            break

        if not user_input:
            continue

        deps = AgentDeps(
            user_id=USER_ID,
            blackboard=Blackboard(),
        )

        response = await supervisor.run(user_input, deps)
        print(f"Assistant: {response}\n")


asyncio.run(main())
```

---

## 21. requirements.txt

```
pydantic-ai
python-dotenv
```

Packages for later stages are added at the start of their respective stages, not here.

---

## 22. Implementation Sequence

**Step 1 — Project scaffold**

Create the full folder structure. Add `__init__.py` to `agents/`, `core/`, `schemas/`.
Create `logs/`, `memory/agents/`, `memory/brain/` directories. Create `.gitignore`
(exclude `.env`, `logs/`, `data/`, `__pycache__/`, `*.pyc`).

**Step 2 — core/logger.py**

Implement first — every other file imports from it. Verify `logs/assistant.log` is
created on import and the format is correct.

**Step 3 — schemas/**

Implement each schema file in order: `message.py` → `agent_task.py` → `turn_record.py`
→ `task_item.py` → `calendar_event.py` → `session_history.py` → `__init__.py`.
Verify `from schemas import Message, AgentTask, TurnRecord` imports cleanly.

**Step 4 — core/deps.py**

Implement `AgentDeps`. Verify it instantiates with only `user_id` provided — all
other fields default correctly.

**Step 5 — core/llm_factory.py**

Implement. Verify `LLMFactory().get_model()` returns a model object without raising.
Confirm the correct provider branch is taken based on `LLM_ORGANIZATION` in `.env`.

**Step 6 — core/blackboard.py**

Implement. Verify `write` then `read` returns the same value. `read` on a missing key
returns the default. `clear` empties the store.

**Step 7 — agents/base.py**

Implement. It is abstract — do not instantiate directly. Verify the import works.

**Step 8 — memory files**

Write `memory/agents/supervisor.md` and `memory/brain/user.md` with the content from
Sections 18 and 19.

**Step 9 — agents/supervisor.py**

Implement. All dependencies are in place at this point.

**Step 10 — main.py**

Implement. Run `python main.py`. Type a message. Confirm:
- Response appears in terminal
- `logs/assistant.log` exists and contains the log lines
- Log format matches `%(asctime)s [%(levelname)s] %(name)s | %(message)s`
- `memory/agents/supervisor.md` persona is active (agent stays concise and direct)

---

## 23. Done When

- `python main.py` runs without error
- A typed message receives a coherent response from the LLM
- `logs/assistant.log` is written with the correct format after every exchange
- `from schemas import Message, AgentTask, TurnRecord, TaskItem, CalendarEvent, SessionHistory` imports cleanly
- `LLMFactory().get_model()` returns without raising
- `Blackboard().write("x", 1)` followed by `.read("x")` returns `1`
- `memory/agents/supervisor.md` persona is loaded and shapes the Supervisor's behaviour
- No Redis, no SQLite, no Telegram, no MCP — none required or referenced this stagee 