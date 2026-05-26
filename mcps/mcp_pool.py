import os
from pydantic_ai.mcp import MCPServerStdio

from mcps.google import google_workspace_server

_servers: dict[str, MCPServerStdio] = {}

def get_pool_server(services: list[str], user_email: str) -> MCPServerStdio:
    """
    Start the MCP server once at application startup and reuse it across all specialists:
    """
    key = f"{user_email}:{'_'.join(sorted(services))}"
    if key not in _servers:
        _servers[key] = google_workspace_server(services, user_email)

    return _servers[key]