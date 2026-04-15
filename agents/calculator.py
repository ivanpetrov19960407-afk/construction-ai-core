"""Агент Calculator — детерминированные расчёты КС-2/КС-3."""

from __future__ import annotations

import math
from datetime import date
from difflib import get_close_matches
from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter
from scripts.rates_catalog import RATES


class CalculatorAgent(BaseAgent):
    """🧮 Calculator — вычисления без использования LLM."""

    system_prompt = "Ты — Calculator агент. Выполняй только детерминированные расчёты."

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="08", llm_router=llm_router)

    def _find_rate(self, work_type: str) -> dict[str, float | str] | None:
        normalized_query = work_type.strip().lower()
        if not normalized_query:
            return None

        names = [str(rate["name"]) for rate in RATES]
        lower_to_rate = {name.lower(): rate for name, rate in zip(names, RATES, strict=False)}

        for name, rate in zip(names, RATES, strict=False):
            if normalized_query in name.lower() or name.lower() in normalized_query:
                return rate

        close = get_close_matches(normalized_query, list(lower_to_rate.keys()), n=1, cutoff=0.35)
        if close:
            return lower_to_rate[close[0]]
        return None

    def _apply_index(self, base_cost: float, region: str = "Москва") -> float:
        indices = {"москва": 1.0, "мо": 0.95, "спб": 0.92}
        index = indices.get(region.strip().lower(), 0.85)
        return round(base_cost * index, 2)

    def _calculate_estimate(self, work_items: list[dict[str, Any]]) -> dict[str, Any]:
        estimate_items: list[dict[str, Any]] = []
        total_cost = 0.0
        total_labor = 0.0

        for item in work_items:
            work_type = str(item.get("work_type", "")).strip()
            volume = float(item.get("volume", 0.0))
            input_unit = str(item.get("unit", "")).strip()
            matched_rate = self._find_rate(work_type)

            if matched_rate is None:
                estimate_items.append(
                    {
                        "work_type": work_type,
                        "volume": volume,
                        "unit": input_unit,
                        "rate_found": False,
                        "message": "Расценка не найдена",
                    }
                )
                continue

            rate_rub = float(matched_rate["rate_rub"])
            labor_hours = float(matched_rate["labor_hours"])
            subtotal_cost = round(rate_rub * volume, 2)
            subtotal_labor = round(labor_hours * volume, 2)

            total_cost += subtotal_cost
            total_labor += subtotal_labor

            estimate_items.append(
                {
                    "code": str(matched_rate["code"]),
                    "name": str(matched_rate["name"]),
                    "work_type": work_type,
                    "unit": str(matched_rate["unit"]),
                    "input_unit": input_unit,
                    "volume": volume,
                    "rate_rub": rate_rub,
                    "labor_hours": labor_hours,
                    "total_cost": subtotal_cost,
                    "total_labor_hours": subtotal_labor,
                    "rate_found": True,
                }
            )

        return {
            "items": estimate_items,
            "total_cost": round(total_cost, 2),
            "total_labor_hours": round(total_labor, 2),
        }

    def _period_days(self, state: dict[str, Any]) -> int:
        period_from = state.get("period_from")
        period_to = state.get("period_to")
        if isinstance(period_from, str) and isinstance(period_to, str):
            start = date.fromisoformat(period_from)
            end = date.fromisoformat(period_to)
            return max((end - start).days + 1, 1)
        return 1

    async def _run(self, state: dict[str, Any]) -> dict[str, Any]:
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
