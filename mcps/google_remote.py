"""
Google's official remote Workspace MCP servers. Each service has a dedicated
endpoint. Authentication is handled via OAuth 2.0 — the same credentials already
configured for the Google Cloud project.
"""

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