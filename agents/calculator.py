"""Агент Calculator — детерминированные расчёты."""

from __future__ import annotations

import ast
from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter

_ALLOWED_BIN_OPS: tuple[type[ast.operator], ...] = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Pow,
    ast.Mod,
)
_ALLOWED_UNARY_OPS: tuple[type[ast.unaryop], ...] = (ast.UAdd, ast.USub)


class CalculatorAgent(BaseAgent):
    """🧮 Calculator — детерминированные вычисления без eval."""

    system_prompt = (
        "Ты — Calculator агент. Объясни расчёты на основе уже вычисленных "
        "детерминированных результатов и представь вывод в табличной форме."
    )

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="08", llm_router=llm_router)

    def _safe_eval(self, expression: str, values: dict[str, float]) -> float:
        node = ast.parse(expression, mode="eval")

        def _eval(expr: ast.AST) -> float:
            if isinstance(expr, ast.Expression):
                return _eval(expr.body)
            if isinstance(expr, ast.Constant) and isinstance(expr.value, (int, float)):
                return float(expr.value)
            if isinstance(expr, ast.Name):
                if expr.id not in values:
                    raise ValueError(f"Unknown variable: {expr.id}")
                return float(values[expr.id])
            if isinstance(expr, ast.BinOp) and isinstance(expr.op, _ALLOWED_BIN_OPS):
                left = _eval(expr.left)
                right = _eval(expr.right)
                if isinstance(expr.op, ast.Add):
                    return left + right
                if isinstance(expr.op, ast.Sub):
                    return left - right
                if isinstance(expr.op, ast.Mult):
                    return left * right
                if isinstance(expr.op, ast.Div):
                    return left / right
                if isinstance(expr.op, ast.Pow):
                    return left**right
                if isinstance(expr.op, ast.Mod):
                    return left % right
            if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, _ALLOWED_UNARY_OPS):
                value = _eval(expr.operand)
                return value if isinstance(expr.op, ast.UAdd) else -value
            raise ValueError(f"Unsupported expression: {expression}")

        return _eval(node)

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        calc_params = state.get("calculation_params", {})
        if not isinstance(calc_params, dict):
            raise TypeError("state['calculation_params'] must be a dict")

        formulas = calc_params.get("formulas", {})
        values = calc_params.get("values", {})
        if not isinstance(formulas, dict) or not isinstance(values, dict):
            raise TypeError("calculation_params must contain dicts 'formulas' and 'values'")

        numeric_values = {k: float(v) for k, v in values.items()}
        results: dict[str, float] = {}
        for key, expr in formulas.items():
            if not isinstance(expr, str):
                raise TypeError("Each formula must be a string")
            results[key] = self._safe_eval(expr, numeric_values | results)

        state["calculation_results"] = results
        prompt = f"Исходные данные: {numeric_values}. Результаты: {results}."
        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)
        return self._update_state(state, response.text)
