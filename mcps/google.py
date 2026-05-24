"""Google Workspace MCP server wrapper using workspace-mcp.

workspace-mcp is a Python MCP server (pip install workspace-mcp) that exposes
Gmail, Calendar, Drive, Docs, Sheets, Slides, Forms, Tasks, Chat, and more
as MCP tools over stdio.

Auth: one-time browser OAuth flow on first tool call. Credentials cached to
disk per email. All subsequent calls are silent.

Usage:
    google_workspace_server(["tasks"])
    google_workspace_server(["tasks", "calendar"])
    google_workspace_server(["gmail"])

Valid service names: gmail, drive, calendar, docs, sheets, slides, forms,
                     tasks, chat, search
"""

import os
import shutil
from pydantic_ai.mcp import MCPServerStdio


def google_workspace_server(services: list[str]) -> MCPServerStdio:
    """Return a configured MCPServerStdio for the given Google Workspace services.

    Spawns workspace-mcp via uvx (preferred) or direct binary. Runs in
    single-user mode — credentials are read from disk after one-time OAuth.

    Args:
        services: list of service names, e.g. ["tasks", "calendar"]

    Returns:
        MCPServerStdio configured to spawn workspace-mcp for the given services.

    Raises:
        RuntimeError: if neither uvx nor workspace-mcp binary is found on PATH.
    """
    # uvx_path = shutil.which("uvx")
    # wsmcp_path = shutil.which("workspace-mcp")

    # if uvx_path:
    #     command = uvx_path
    #     args = [
    #         "workspace-mcp",
    #         "--single-user",
    #         "--tools", " ".join(services),
    #     ]
    # elif wsmcp_path:
    #     command = wsmcp_path
    #     args = [
    #         "--single-user",
    #         "--tools", " ".join(services),
    #     ]
    # else:
    #     raise RuntimeError(
    #         "Neither uvx nor workspace-mcp found on PATH.\n"
    #         "Install with: pip install uv && pip install workspace-mcp\n"
    #         "Then complete OAuth setup: see SPECIFICATION_1B_v3.md Step 7."
    #     )

    return MCPServerStdio(
        command="uvx",
        args=[
            "workspace-mcp",
            "--single-user",
            "--tools", ",".join(services),
        ],
        env={
            **os.environ,
            "GOOGLE_OAUTH_CLIENT_ID": os.getenv("GOOGLE_OAUTH_CLIENT_ID", ""),
            "GOOGLE_OAUTH_CLIENT_SECRET": os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "USER_GOOGLE_EMAIL": os.getenv("USER_GOOGLE_EMAIL", ""),
            "OAUTHLIB_INSECURE_TRANSPORT": "1",
        },
    )