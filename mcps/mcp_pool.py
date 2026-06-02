import os
from typing import Any, Dict
from pydantic_ai.mcp import MCPServerStdio
from mcps.google import google_workspace_server
from schemas.agent_registration import AgentRegistration

# Shared runtime memory map tracking open server subprocess channels
_servers: Dict[str, Any] = {}

def get_pool_server(registration: AgentRegistration, user_email: str) -> Any:
    """
    Polymorphic connection pool manager.
    Consumes the complete 12-field AgentRegistration block to route and configure server instances.
    """
    # Route 1: Local execution contexts requiring zero background subprocess tooling
    if registration.server_type == "none":
        return None

    # Route 2: Isolated standard IO external processes managed via custom platform tools
    if registration.server_type == "stdio":
        # Key configurations using command sequence vectors to handle shared instances cleanly
        cache_key = f"stdio:{registration.mcp_command}:{'_'.join(registration.mcp_args)}"
        
        if cache_key not in _servers:
            if not registration.mcp_command:
                raise ValueError(f"Agent '{registration.key}' missing required mcp_command parameter.")

            # Isolate environment properties explicitly to control security leakage vectors
            injected_env = {}
            for env_key in registration.mcp_env_keys:
                val = os.getenv(env_key)
                if val:
                    injected_env[env_key] = val
                else:
                    raise RuntimeError(f"Missing required execution credential token: {env_key}")
            
            # Merge context limits with host path parameters to maintain binary lookups
            server_env = {**os.environ, **injected_env}

            # Instantiate standard pipe stream inside PydanticAI boundary controls
            _servers[cache_key] = MCPServerStdio(
                command=registration.mcp_command,
                args=registration.mcp_args,
                server_env=server_env
            )
        return _servers[cache_key]

    # Route 3: Legacy Google Workspace shared server mapping fallback tracks
    if not registration.services:
        return None
        
    cache_key = f"google:{user_email}:{'_'.join(sorted(registration.services))}"
    if cache_key not in _servers:
        _servers[cache_key] = google_workspace_server(registration.services, user_email)

    return _servers[cache_key]