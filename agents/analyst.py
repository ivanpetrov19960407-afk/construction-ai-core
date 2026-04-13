"""Агент Analyst — анализ документации, выявление противоречий и рисков."""

from __future__ import annotations

import re
from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter


class AnalystAgent(BaseAgent):
    """📊 Analyst — выявляет противоречия и формирует отчёт о рисках."""

    system_prompt = (
        "Ты — эксперт по тендерному законодательству (44-ФЗ, 223-ФЗ). "
        "Выяви риски, противоречия, нарушения. Структурируй ответ строго: "
        "РИСКИ: ..., НЕСООТВЕТСТВИЯ: ..., РЕКОМЕНДАЦИЯ: ..."
    )

    _RISKS_RE = re.compile(
        r"РИСКИ\s*:\s*(.*?)(?=\n\s*НЕСООТВЕТСТВИЯ\s*:|$)",
        re.IGNORECASE | re.DOTALL,
    )
    _CONTRADICTIONS_RE = re.compile(
        r"НЕСООТВЕТСТВИЯ\s*:\s*(.*?)(?=\n\s*РЕКОМЕНДАЦИЯ\s*:|$)",
        re.IGNORECASE | re.DOTALL,
    )
    _RECOMMENDATION_RE = re.compile(r"РЕКОМЕНДАЦИЯ\s*:\s*(.+)$", re.IGNORECASE | re.DOTALL)

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="02", llm_router=llm_router)

    async def _run(self, state: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(state)
        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)

        risk_report = response.text
        state["risk_report"] = risk_report
        state["risks"] = self._extract_section_items(self._RISKS_RE, risk_report)
        state["contradictions"] = self._extract_section_items(self._CONTRADICTIONS_RE, risk_report)

        recommendation_match = self._RECOMMENDATION_RE.search(risk_report)
        if recommendation_match:
            state["analyst_recommendation"] = recommendation_match.group(1).strip()

        return self._update_state(state, risk_report)

    @staticmethod
    def _extract_section_items(pattern: re.Pattern[str], text: str) -> list[str]:
        match = pattern.search(text)
        if not match:
            return []

        section = match.group(1).strip()
        if not section:
            return []

        items: list[str] = []
        for raw_item in re.split(r"\n|;", section):
            normalized = raw_item.strip().strip("-•")
            if normalized and normalized not in items:
                items.append(normalized)
        return items
