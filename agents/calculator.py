"""Агент Calculator — детерминированные расчёты КС-2/КС-3."""

from __future__ import annotations

import math
from datetime import date
from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter


class CalculatorAgent(BaseAgent):
    """🧮 Calculator — вычисления без использования LLM."""

    system_prompt = "Ты — Calculator агент. Выполняй только детерминированные расчёты."

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="08", llm_router=llm_router)

    def _period_days(self, state: dict[str, Any]) -> int:
        period_from = state.get("period_from")
        period_to = state.get("period_to")
        if isinstance(period_from, str) and isinstance(period_to, str):
            start = date.fromisoformat(period_from)
            end = date.fromisoformat(period_to)
            return max((end - start).days + 1, 1)
        return 1

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        calc_params = state.get("calculation_params", {})
        if not isinstance(calc_params, dict):
            raise TypeError("state['calculation_params'] must be a dict")

        work_items = calc_params.get("work_items", [])
        if not isinstance(work_items, list):
            raise TypeError("calculation_params['work_items'] must be a list")

        ks2_items: list[dict[str, Any]] = []
        total_cost = 0.0
        total_hours = 0.0

        for idx, item in enumerate(work_items, start=1):
            if not isinstance(item, dict):
                raise TypeError("Each work item must be a dict")

            volume = float(item["volume"])
            norm_hours = float(item["norm_hours"])
            price_per_unit = float(item["price_per_unit"])

            subtotal_cost = volume * price_per_unit
            subtotal_hours = volume * norm_hours

            total_cost += subtotal_cost
            total_hours += subtotal_hours

            ks2_items.append(
                {
                    "index": idx,
                    "name": str(item["name"]),
                    "unit": str(item["unit"]),
                    "volume": volume,
                    "norm_hours": norm_hours,
                    "price_per_unit": price_per_unit,
                    "subtotal_cost": subtotal_cost,
                    "subtotal_hours": subtotal_hours,
                }
            )

        period_days = self._period_days(state)
        workers_needed = math.ceil(total_hours / (period_days * 8)) if total_hours > 0 else 0

        state["ks2_data"] = {
            "work_items": ks2_items,
            "total_cost": total_cost,
            "total_hours": total_hours,
        }
        state["ks3_data"] = {
            "period_days": period_days,
            "total_cost": total_cost,
            "total_hours": total_hours,
            "workers_needed": workers_needed,
        }

        return self._update_state(
            state,
            (
                f"Calculated: total_cost={total_cost:.2f}, total_hours={total_hours:.2f}, "
                f"workers_needed={workers_needed}"
            ),
        )
