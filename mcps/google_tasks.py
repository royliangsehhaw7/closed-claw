from __future__ import annotations

import os
from dotenv import load_dotenv
from pydantic_ai.mcp import MCPServerStdio

load_dotenv()


def google_tasks_server() -> MCPServerStdio:
    """Return a configured MCPServerStdio for Google Tasks.

    PydanticAI uses this to spawn the MCP server subprocess and discover
    its tools. In Stage 1b, test scripts use the connection directly.
    In Stage 1c, this is passed to Agent(mcp_servers=[google_tasks_server()])
    and PydanticAI handles all tool calls automatically.
    """
    return MCPServerStdio(
        "uvx",
        args=[
            "mcp-server-google-workspace",
            "--service", "tasks",
            "--credentials", os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/credentials.json"),
            "--token", os.getenv("GOOGLE_TOKEN_PATH", "credentials/token.json"),
        ],
    )


# ===== using MCPToolSet, mcp are used as tools instead of mcp_servers in agents ===== #
# from pydantic_ai.mcp import MCPToolset
# def google_tasks_server() -> MCPToolset:
#     """Return a configured MCPToolset for Google Tasks.

#     PydanticAI uses this to connect to the MCP server subprocess and discover
#     its tools. In Stage 1b, test scripts use the connection directly.
#     In Stage 1c, this is passed to Agent(toolsets=[google_tasks_server()])
#     and PydanticAI handles all tool calls automatically.
#     """
#     return MCPToolset(
#         ("uvx", [
#             "mcp-server-google-workspace",
#             "--service", "tasks",
#             "--credentials", os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/credentials.json"),
#             "--token", os.getenv("GOOGLE_TOKEN_PATH", "credentials/token.json"),
#         ])
#     )