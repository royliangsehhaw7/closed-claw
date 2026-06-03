from __future__ import annotations

import os
from core.logger import logger
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
        if not os.getenv("TRELLO_API_KEY") or not os.getenv("TRELLO_TOKEN"):
            logger.error("mcp_pool | Trello credentials not set — skipping server")
            return None
        
        return trello_server(user_email)

    raise ValueError(f"No stdio server factory for services: {registration.services}")