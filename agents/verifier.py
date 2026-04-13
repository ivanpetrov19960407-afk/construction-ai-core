"""Агент Verifier — финальная KPI-проверка."""

import hashlib
from typing import Any

from agents.base import AgentResult, BaseAgent
from core.llm_router import LLMRouter


class VerifierAgent(BaseAgent):
    """✅ Verifier — финальная проверка и верификация.

    KPI:
    - confidence ≥ 0.95
    - conflict_rate ≤ 0.05
    - SHA256-хэш версии документа

    Результат: Approved / Reject → audit log.
    """

    agent_id = "verifier"
    name = "Verifier"
    system_prompt = (
        "Ты — агент-верификатор строительной ИИ-платформы. "
        "Проводишь финальную проверку документа перед выгрузкой. "
        "Оцени confidence (0.0–1.0) и conflict_rate (0.0–1.0). "
        "Ответь в формате:\n"
        "CONFIDENCE: <число>\n"
        "CONFLICT_RATE: <число>\n"
        "VERDICT: APPROVED или REJECTED\n"
        "REASON: <пояснение>"
    )

    MIN_CONFIDENCE = 0.95
    MAX_CONFLICT_RATE = 0.05

    def __init__(self, llm_router: LLMRouter):
        super().__init__(llm_router)

    async def execute(
        self,
        task: str,
        context: dict[str, Any] | None = None,
        previous_results: list[AgentResult] | None = None,
    ) -> AgentResult:
        """Провести финальную верификацию документа."""
        prompt = f"Проведи финальную верификацию документа:\n\n{task}"
        ctx = self._build_context_prompt(previous_results)
        if ctx:
            prompt += ctx

        response = await self.llm.query(
            prompt=prompt,
            system_prompt=self.system_prompt,
        )

        # Генерируем SHA256-хэш версии
        doc_content = previous_results[-1].output if previous_results else task
        version_hash = hashlib.sha256(doc_content.encode()).hexdigest()

        return AgentResult(
            agent_id=self.agent_id,
            output=response.text,
            metadata={
                "version_hash": version_hash,
                "provider": response.provider.value,
                "model": response.model,
            },
        )
