"""Базовые контракты для инструментов retrieval."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class BaseTool(ABC):
    """Абстрактный базовый класс для tool-интерфейсов."""

    @abstractmethod
    async def run(self, query: str, **kwargs: Any) -> list[dict[str, Any]]:
        """Выполнить инструмент и вернуть список нормализованных результатов."""
