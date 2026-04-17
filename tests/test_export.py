"""Тесты экспорта в XML для 1С."""

from __future__ import annotations

import asyncio
import xml.etree.ElementTree as ET

from core.export.onec_exporter import OneCExporter


def test_ks2_xml_structure(monkeypatch):
    """КС-2 экспортируется с ключевыми тегами 1С."""

    async def _mock_fetch_generated_doc(doc_id: str, doc_type: str, org_id: str) -> dict:
        assert doc_id == "doc-001"
        assert doc_type == "ks2"
        assert org_id == "default"
        return {
            "number": "КС2-77",
            "date": "2026-04-01",
            "organization": "ООО Строймонтаж",
            "object": "ЖК Север",
            "work_items": [
                {
                    "name": "Кладка стен",
                    "unit": "м2",
                    "quantity": 10,
                    "price": 1500,
                    "amount": 15000,
                }
            ],
        }

    exporter = OneCExporter()
    monkeypatch.setattr(exporter, "_fetch_generated_doc", _mock_fetch_generated_doc)

    xml_bytes = asyncio.run(exporter.export_ks2_to_xml(doc_id="doc-001"))
    root = ET.fromstring(xml_bytes)

    assert root.tag == "КС2"
    assert root.findtext("Номер") == "КС2-77"
    assert root.findtext("Организация") == "ООО Строймонтаж"
    assert root.find("ВидыРабот") is not None
    assert root.find("ВидыРабот/ВидРаботы/Наименование") is not None
    assert root.findtext("Итого") == "15000.00"


def test_ks2_xml_keeps_explicit_zero_amount(monkeypatch):
    """Если amount=0 указан явно, он не должен заменяться quantity*price."""

    async def _mock_fetch_generated_doc(doc_id: str, doc_type: str, org_id: str) -> dict:
        assert doc_id == "doc-zero"
        assert doc_type == "ks2"
        assert org_id == "default"
        return {
            "number": "КС2-0",
            "date": "2026-04-01",
            "organization": "ООО Строймонтаж",
            "object": "ЖК Север",
            "work_items": [
                {
                    "name": "Корректировка",
                    "unit": "шт",
                    "quantity": 2,
                    "price": 100,
                    "amount": 0,
                }
            ],
        }

    exporter = OneCExporter()
    monkeypatch.setattr(exporter, "_fetch_generated_doc", _mock_fetch_generated_doc)

    xml_bytes = asyncio.run(exporter.export_ks2_to_xml(doc_id="doc-zero"))
    root = ET.fromstring(xml_bytes)

    assert root.findtext("ВидыРабот/ВидРаботы/Сумма") == "0.00"
    assert root.findtext("Итого") == "0.00"


def test_m29_xml_period_filter(monkeypatch):
    """Экспорт М-29 использует период YYYY-MM при выборке KG записей."""
    requested_periods: list[str] = []

    async def _mock_fetch_kg_entries(project_id: str, period: str) -> list[dict]:
        assert project_id == "project-1"
        requested_periods.append(period)
        return [{"material_id": "mat-1", "material_name": "Цемент", "unit": "кг", "quantity": 2}]

    async def _mock_fetch_material_passports(project_id: str) -> list[dict]:
        assert project_id == "project-1"
        return [{"material_id": "mat-1", "name": "Цемент М500", "unit": "кг", "price": 350}]

    exporter = OneCExporter()
    monkeypatch.setattr(exporter, "_fetch_kg_entries", _mock_fetch_kg_entries)
    monkeypatch.setattr(exporter, "_fetch_material_passports", _mock_fetch_material_passports)

    xml_bytes = asyncio.run(exporter.export_m29_to_xml(project_id="project-1", period="2024-12"))
    root = ET.fromstring(xml_bytes)

    assert requested_periods == ["2024-12"]
    assert root.tag == "М29"
    assert root.findtext("Период") == "2024-12"
    assert root.find("Материалы/Материал/Наименование") is not None
