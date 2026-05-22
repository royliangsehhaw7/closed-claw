# from __future__ import annotations

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