"""Агент Formatter — ГОСТ-форматирование DOCX."""

from __future__ import annotations

import re
from typing import Any

from agents.base import BaseAgent
from core.docx_generator import DocxGenerator
from core.llm_router import LLMRouter


class FormatterAgent(BaseAgent):
    """📐 Formatter — готовит финальный DOCX на основе вывода Verifier."""

    system_prompt = "Ты — Formatter агент."

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="07", llm_router=llm_router)
        self.docx_generator = DocxGenerator()

    def _extract_verifier_output(self, state: dict[str, Any]) -> str:
        history = state.get("history", [])
        if not isinstance(history, list):
            return ""

        for item in reversed(history):
            if not isinstance(item, dict):
                continue
            if str(item.get("agent_name", "")).lower() == "verifier":
                return str(item.get("output", ""))
        return ""

    def _extract_by_label(self, text: str, labels: list[str]) -> str:
        escaped = "|".join(re.escape(label) for label in labels)
        pattern = re.compile(
            rf"(?:^|\\n)\s*(?:{escaped})\s*[:\-]?\s*(.+?)(?=\\n\s*[А-ЯA-Z0-9].{{0,40}}[:\-]|\Z)",
            flags=re.IGNORECASE | re.DOTALL,
        )
        match = pattern.search(text)
        if not match:
            return ""
        return " ".join(match.group(1).strip().split())

    def _parse_context(self, verifier_output: str, state: dict[str, Any]) -> dict[str, Any]:
        normative_raw = self._extract_by_label(
            verifier_output,
            ["Нормативные документы", "Нормативные акты", "НПА", "normative_docs"],
        )
        normative_docs = [
            line.strip("•-— ") for line in re.split(r"[\n,;]", normative_raw) if line.strip("•-— ")
        ]

        sha256 = str(state.get("verification", {}).get("sha256", "")).strip()
        if not sha256:
            audit_log = state.get("audit_log", [])
            if isinstance(audit_log, list) and audit_log:
                sha256 = str(audit_log[-1].get("sha256", "")).strip()

        return {
            "work_type": self._extract_by_label(verifier_output, ["Вид работ", "work_type"])
            or str(state.get("title", "Технологическая карта")),
            "scope": self._extract_by_label(verifier_output, ["Область применения", "scope"])
            or "Не указано",
            "technology": self._extract_by_label(
                verifier_output,
                ["Организация и технология производства работ", "Технология", "technology"],
            )
            or "Не указано",
            "quality_requirements": self._extract_by_label(
                verifier_output,
                ["Требования к качеству работ", "Качество", "quality_requirements"],
            )
            or "Не указано",
            "normative_docs": normative_docs or ["Не указано"],
            "sha256": sha256 or "n/a",
        }

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        if "ks2_data" in state and "ks3_data" in state:
            ks2_data = state.get("ks2_data", {})
            ks3_data = state.get("ks3_data", {})
            context = {
                "object_name": state.get("object_name", "Не указан"),
                "contract_number": state.get("contract_number", "Не указан"),
                "period_from": state.get("period_from", ""),
                "period_to": state.get("period_to", ""),
                "work_items": ks2_data.get("work_items", []),
                "total_cost": ks2_data.get("total_cost", 0.0),
                "total_hours": ks2_data.get("total_hours", 0.0),
                "workers_needed": ks3_data.get("workers_needed", 0),
            }
            docx_bytes = self.docx_generator.generate("ks_template", context)
            state["docx_bytes"] = docx_bytes
            state["docx_payload"] = {
                "template": "ks_template",
                "ks2": ks2_data,
                "ks3": ks3_data,
            }
            state["final_output"] = state["docx_payload"]
            return self._update_state(state, "KS DOCX generated")

        verifier_output = self._extract_verifier_output(state)
        response = await self.llm_router.query(
            prompt=verifier_output or str(state.get("message", "")),
            system_prompt=self.system_prompt,
        )
        context = self._parse_context(verifier_output, state)
        docx_bytes = self.docx_generator.generate("tk_template", context)

        state["docx_bytes"] = docx_bytes
        state["final_output"] = {
            "template": "tk_template",
            "context": context,
            "docx_size": len(docx_bytes),
        }

        return self._update_state(state, response.text)
