"""In-memory хранилище истории сообщений сессии."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone


class SessionMemory:
    """Простое in-memory хранилище истории по session_id."""

    def __init__(self, max_messages: int = 50) -> None:
        self.max_messages = max_messages
        self._store: dict[str, list[dict[str, str]]] = defaultdict(list)

    def add(self, session_id: str, role: str, content: str) -> None:
        """Добавить сообщение в историю сессии."""
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        history = self._store[session_id]
        history.append(message)
        if len(history) > self.max_messages:
            del history[0 : len(history) - self.max_messages]

    def get(self, session_id: str, last_n: int = 10) -> list[dict[str, str]]:
        """Вернуть последние N сообщений сессии."""
        history = self._store.get(session_id, [])
        if last_n <= 0:
            return []
        return history[-last_n:]

    def clear(self, session_id: str) -> None:
        """Очистить историю конкретной сессии."""
        self._store.pop(session_id, None)
