# """
# Google Workspace MCP server wrapper using workspace-mcp.

# workspace-mcp is a Python MCP server (pip install workspace-mcp) that exposes
# Gmail, Calendar, Drive, Docs, Sheets, Slides, Forms, Tasks, Chat, and more
# as MCP tools over stdio.

# Auth: one-time browser OAuth flow on first tool call. Credentials cached to
# disk per email. All subsequent calls are silent.

# Usage:
#     google_workspace_server(["tasks"])
#     google_workspace_server(["tasks", "calendar"])
#     google_workspace_server(["gmail"])

# Valid service names: gmail, drive, calendar, docs, sheets, slides, forms,
#                      tasks, chat, search
# """

# import os
# import shutil
# from pydantic_ai.mcp import MCPServerStdio


# def google_workspace_server(services: list[str], user_email: str | None = None, timeout: int = 30) -> MCPServerStdio:
#     """
#     Return a configured MCPServerStdio for the given Google Workspace services.

#     Spawns workspace-mcp via uvx (preferred) or direct binary. Runs in
#     single-user mode — credentials are read from disk after one-time OAuth.

#     Args:
#         services: list of service names, e.g. ["tasks", "calendar"]

#     Returns:
#         MCPServerStdio configured to spawn workspace-mcp for the given services.

#     Raises:
#         RuntimeError: if neither uvx nor workspace-mcp binary is found on PATH.
#     """
#     # 1. Prepare the environment dictionary explicitly
#     # Start with the FULL current environment, then override/add your keys
#     env = {**os.environ}
#     env["GOOGLE_OAUTH_CLIENT_ID"] = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
#     env["GOOGLE_OAUTH_CLIENT_SECRET"] = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
#     env["USER_GOOGLE_EMAIL"] = user_email or os.getenv("USER_GOOGLE_EMAIL", "")
#     env["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

#     # 2. Return the server with the prepared dictionary
#     args = ["workspace-mcp", "--single-user"]
#     for service in services:
#         args.extend(["--tools", service])  # <-- FIX: Separate flags

#     tool_prefix = f"google_{services[0]}_"  # e.g., "google_calendar_", "google_tasks_"

#     return MCPServerStdio(
#         command="uvx",
#         args=args,
#         env=env,
#         timeout=timeout,
#         tool_prefix=tool_prefix
#     )



import os
from pydantic_ai.mcp import MCPServerStdio


def google_workspace_server(
    services: list[str],
    user_email: str | None = None,
    timeout: int = 60,
) -> MCPServerStdio:
    env = {**os.environ}
    env["GOOGLE_OAUTH_CLIENT_ID"] = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "")
    env["GOOGLE_OAUTH_CLIENT_SECRET"] = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "")
    env["USER_GOOGLE_EMAIL"] = user_email or os.getenv("USER_GOOGLE_EMAIL", "")
    env["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    return MCPServerStdio(
        command="uvx",
        args=["workspace-mcp", "--single-user", "--tools"] + services,
        env=env,
        timeout=timeout,
    )