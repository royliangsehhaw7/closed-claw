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