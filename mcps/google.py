# # from __future__ import annotations

# import os
# from dotenv import load_dotenv
# from pydantic_ai.mcp import MCPServerStdio

# load_dotenv()


# def google_workspace_server() -> MCPServerStdio:
#     """Configures the official Workspace MCP server cleanly for PydanticAI."""
#     mcp_env = os.environ.copy()

#     mcp_env.update(
#         {
#             "WORKSPACE_MCP_AUTH_MODE": "service_account",
#             "GOOGLE_APPLICATION_CREDENTIALS": os.getenv("GOOGLE_APPLICATION_CREDENTIALS", ""), 
#             # "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
#             # "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
#             "USER_GOOGLE_EMAIL": os.getenv("GOOGLE_ACCOUNT_EMAIL", ""),
#             "WORKSPACE_MCP_TOOL_TIER": "core",
#             # --- THE FIXES FOR THE BROKEN RESOURCE ERROR ---
#             # Forces FastMCP to suppress text logging or pipe it safely to stderr
#             "FASTMCP_LOG_LEVEL": "WARNING",
#             # Tells UV to keep its mouth shut so it doesn't leak status text into stdout
#             "UV_QUIET": "1",
#         }
#     )

#     return MCPServerStdio(
#         command="uvx",
#         args=["workspace-mcp"],
#         env=mcp_env,
#     )


# from __future__ import annotations

# import os
# from dotenv import load_dotenv
# from pydantic_ai.mcp import MCPServerStdio

# load_dotenv()


# def google_workspace_server() -> MCPServerStdio:
#     """Launches the clean, configuration-driven Node Google Workspace MCP server."""
#     mcp_env = os.environ.copy()

#     # Pass the required scopes directly to the environment
#     mcp_env.update(
#         {
#             "GOOGLE_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
#             "GOOGLE_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
#         }
#     )

#     return MCPServerStdio(
#         command="npx",
#         args=[
#             "-y", 
#             "@modelcontextprotocol/server-google-workspace",
#             "--scopes", "https://www.googleapis.com/auth/tasks", "https://www.googleapis.com/auth/calendar"
#         ],
#         env=mcp_env,
#     )


from __future__ import annotations

import os
from dotenv import load_dotenv
from pydantic_ai.mcp import MCPServerStdio

load_dotenv()


def google_workspace_server(tools: list[str]) -> MCPServerStdio:
    """Return a configured MCPServerStdio for the given Google Workspace services.

    workspace-mcp is a single package that covers all 12 Google services.
    The `tools` argument scopes the server to only the services needed by the
    caller — this avoids loading unnecessary API scopes.

    PydanticAI uses this to spawn the MCP server subprocess and discover its
    tools. In Stage 1b, test scripts use the connection directly for verification.
    In Stage 1c, this is passed to Agent(mcp_servers=[...]) and PydanticAI handles
    all tool discovery and calling automatically.

    Args:
        tools: list of Google service names to enable, e.g. ["tasks", "calendar"]
               Valid values: gmail, calendar, tasks, drive, docs, sheets, slides,
               forms, chat, contacts, search

    Usage:
        google_workspace_server(["tasks", "calendar"])  # Concierge agent
        google_workspace_server(["gmail"])               # Comms agent
    """
    return MCPServerStdio(
        "uvx",
        args=["workspace-mcp", "--tools"] + tools,
        env={
            **os.environ,
            "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "USER_GOOGLE_EMAIL": os.getenv("GOOGLE_ACCOUNT_EMAIL", ""),
            "OAUTHLIB_INSECURE_TRANSPORT": "1",
        },
    )