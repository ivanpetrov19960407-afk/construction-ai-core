"""Тесты сметных расценок в CalculatorAgent."""

from agents.calculator import CalculatorAgent
from core.llm_router import LLMRouter


class DummyRouter(LLMRouter):
    """Тестовый роутер без сетевых вызовов."""


def test_find_rate_by_work_type():
    """Поиск по work_type 'бетонирование' находит ГЭСН 06-01-001."""
    agent = CalculatorAgent(DummyRouter())

    rate = agent._find_rate("бетонирование")

    assert rate is not None
    assert rate["code"] == "ГЭСН 06-01-001"


def test_calculate_estimate_returns_total():
    """Калькулятор возвращает общую стоимость и трудозатраты по позициям."""
    agent = CalculatorAgent(DummyRouter())
    result = agent._calculate_estimate(
        [
            {"work_type": "бетонирование", "volume": 10.0, "unit": "м³"},
            {"work_type": "кладка стен из кирпича", "volume": 5.0, "unit": "м³"},
        ]
    )

    assert len(result["items"]) == 2
    assert result["total_cost"] > 0
    assert result["total_labor_hours"] > 0


def test_apply_region_index():
    """Проверка регионального индекса пересчёта."""
    agent = CalculatorAgent(DummyRouter())

    assert agent._apply_index(1000.0, "Москва") == 1000.0
    assert agent._apply_index(1000.0, "МО") == 950.0
    assert agent._apply_index(1000.0, "СПб") == 920.0
    assert agent._apply_index(1000.0, "Тверь") == 850.0
