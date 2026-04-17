"""Экспорт документов в XML-формат для 1С."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from sqlalchemy import create_engine, text

from config.settings import settings


class OneCExporter:
    """Экспортёр КС-2 и М-29 в XML, совместимый с 1С."""

    async def export_ks2_to_xml(self, doc_id: str, org_id: str = "default") -> bytes:
        """Выгрузить КС-2 из generated_docs в XML-формат 1С."""
        document = await self._fetch_generated_doc(doc_id=doc_id, doc_type="ks2", org_id=org_id)
        if document is None:
            raise ValueError(f"KS2 document not found for doc_id={doc_id} and org_id={org_id}")

        root = ET.Element("КС2")
        ET.SubElement(root, "Номер").text = str(document.get("number") or doc_id)
        ET.SubElement(root, "Дата").text = str(document.get("date") or "")
        ET.SubElement(root, "Организация").text = str(document.get("organization") or "")
        ET.SubElement(root, "Объект").text = str(document.get("object") or "")

        works_node = ET.SubElement(root, "ВидыРабот")
        total_sum = Decimal("0")
        for item in self._normalize_work_items(document):
            work_node = ET.SubElement(works_node, "ВидРаботы")
            quantity = self._to_decimal(item.get("quantity"))
            price = self._to_decimal(item.get("price"))
            amount_value = item.get("amount")
            amount = (
                quantity * price
                if amount_value is None or amount_value == ""
                else self._to_decimal(amount_value)
            )
            total_sum += amount

            ET.SubElement(work_node, "Наименование").text = str(item.get("name") or "")
            ET.SubElement(work_node, "Ед").text = str(item.get("unit") or "")
            ET.SubElement(work_node, "Количество").text = self._decimal_to_str(quantity)
            ET.SubElement(work_node, "Цена").text = self._decimal_to_str(price)
            ET.SubElement(work_node, "Сумма").text = self._decimal_to_str(amount)

        ET.SubElement(root, "Итого").text = self._decimal_to_str(total_sum)
        return self._to_xml_bytes(root)

    async def export_m29_to_xml(self, project_id: str, period: str) -> bytes:
        """Экспортировать М-29 (списание материалов) за период YYYY-MM."""
        self._validate_period(period)
        entries = await self._fetch_kg_entries(project_id=project_id, period=period)
        passports = await self._fetch_material_passports(project_id=project_id)
        passport_by_material = {
            str(row.get("material_id")): row
            for row in passports
            if row.get("material_id") is not None
        }

        root = ET.Element("М29")
        ET.SubElement(root, "Проект").text = str(project_id)
        ET.SubElement(root, "Период").text = period
        materials_node = ET.SubElement(root, "Материалы")

        total_amount = Decimal("0")
        for entry in entries:
            material_id = str(entry.get("material_id") or "")
            passport = passport_by_material.get(material_id, {})

            quantity = self._to_decimal(entry.get("quantity"))
            price = self._to_decimal(passport.get("price"))
            amount = quantity * price
            total_amount += amount

            material_node = ET.SubElement(materials_node, "Материал")
            ET.SubElement(material_node, "Код").text = material_id
            ET.SubElement(material_node, "Наименование").text = str(
                passport.get("name") or entry.get("material_name") or ""
            )
            ET.SubElement(material_node, "Ед").text = str(
                passport.get("unit") or entry.get("unit") or ""
            )
            ET.SubElement(material_node, "Количество").text = self._decimal_to_str(quantity)
            ET.SubElement(material_node, "Цена").text = self._decimal_to_str(price)
            ET.SubElement(material_node, "Сумма").text = self._decimal_to_str(amount)

        ET.SubElement(root, "Итого").text = self._decimal_to_str(total_amount)
        return self._to_xml_bytes(root)

    async def _fetch_generated_doc(self, doc_id: str, doc_type: str, org_id: str) -> dict | None:
        query = text(
            """
            SELECT payload
            FROM generated_docs
            WHERE id = :doc_id
              AND type = :doc_type
              AND org_id = :org_id
            LIMIT 1
            """
        )
        engine = create_engine(settings.database_url, future=True)
        with engine.connect() as conn:
            row = conn.execute(
                query,
                {"doc_id": doc_id, "doc_type": doc_type, "org_id": org_id},
            ).mappings().first()
        if row is None:
            return None
        payload = row.get("payload")
        return self._ensure_dict(payload)

    async def _fetch_kg_entries(self, project_id: str, period: str) -> list[dict]:
        query = text(
            """
            SELECT material_id, material_name, unit, quantity
            FROM kg_entries
            WHERE project_id = :project_id
              AND strftime('%Y-%m', COALESCE(actual_date, planned_date, created_at)) = :period
            ORDER BY material_id
            """
        )
        engine = create_engine(settings.database_url, future=True)
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    query,
                    {"project_id": project_id, "period": period},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    async def _fetch_material_passports(self, project_id: str) -> list[dict]:
        query = text(
            """
            SELECT material_id, name, unit, price
            FROM material_passports
            WHERE project_id = :project_id
            """
        )
        engine = create_engine(settings.database_url, future=True)
        with engine.connect() as conn:
            rows = conn.execute(query, {"project_id": project_id}).mappings().all()
        return [dict(row) for row in rows]

    @staticmethod
    def _normalize_work_items(document: dict) -> list[dict]:
        work_items = (
            document.get("work_items") or document.get("works") or document.get("items") or []
        )
        if isinstance(work_items, list):
            return [item for item in work_items if isinstance(item, dict)]
        return []

    @staticmethod
    def _to_xml_bytes(root: ET.Element) -> bytes:
        return ET.tostring(root, encoding="utf-8", xml_declaration=True)

    @staticmethod
    def _validate_period(period: str) -> None:
        if len(period) != 7 or period[4] != "-":
            raise ValueError("Period must be in YYYY-MM format")

    @staticmethod
    def _ensure_dict(payload: str | bytes | dict | None) -> dict:
        if isinstance(payload, dict):
            return payload
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        if isinstance(payload, str) and payload:
            loaded = json.loads(payload)
            if isinstance(loaded, dict):
                return loaded
        return {}

    @staticmethod
    def _to_decimal(value: object) -> Decimal:
        if isinstance(value, Decimal):
            return value
        if value is None or value == "":
            return Decimal("0")
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    @staticmethod
    def _decimal_to_str(value: Decimal) -> str:
        return format(value.quantize(Decimal("0.01")), "f")
