"""Агент Verifier — финальная KPI-проверка."""

from __future__ import annotations

import hashlib
from typing import Any


from agents.base import BaseAgent
from core.llm_router import LLMRouter


class VerifierAgent(BaseAgent):
    """✅ Verifier — проверка KPI и аудит."""

    system_prompt = (
        "Ты — Verifier агент. Проведи финальную верификацию и кратко обоснуй результат "
        "по метрикам confidence и conflict_rate."
    )
    MIN_CONFIDENCE = 0.95
    MAX_CONFLICT_RATE = 0.05

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="05", llm_router=llm_router)

    @staticmethod
    def _resolve_recommendation(confidence: float, risks: list[str]) -> str:
        if confidence >= 0.85 and len(risks) <= 2:
            return "УЧАСТВОВАТЬ"
        if confidence < 0.7 or len(risks) > 5:
            return "НЕ УЧАСТВОВАТЬ"
        return "УТОЧНИТЬ"

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        confidence = float(state.get("confidence", 0.0))
        conflict_rate = float(state.get("conflict_rate", 1.0))

        prompt = self._build_prompt(state)
        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)

        final_text = str(state.get("final_text") or state.get("draft") or "")
        version_hash = hashlib.sha256(final_text.encode("utf-8")).hexdigest()

        approved = confidence >= self.MIN_CONFIDENCE and conflict_rate <= self.MAX_CONFLICT_RATE
        risks = state.get("risks", [])
        if not isinstance(risks, list):
            risks = []
        recommendation = self._resolve_recommendation(confidence, [str(item) for item in risks])
        audit_entry = {
            "agent": self.agent_id,
            "confidence": confidence,
            "conflict_rate": conflict_rate,
            "approved": approved,
            "sha256": version_hash,
        }

        audit_log = state.setdefault("audit_log", [])
        if not isinstance(audit_log, list):
            raise TypeError("state['audit_log'] must be a list")
        audit_log.append(audit_entry)
        state["audit_log"] = audit_log
        state["verification"] = {
            "approved": approved,
            "sha256": version_hash,
            "details": response.text,
            "recommendation": recommendation,
        }
        state["recommendation"] = recommendation

        return self._update_state(state, response.text)
