"""GSN readiness checks against Rostechnadzor order №522-pr requirements."""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from config.settings import settings
from core.projects import ProjectDocument, get_projects_sessionmaker

# Требования Приказа №522-пр по каждому разделу
GSN_REQUIREMENTS = {
    "KZH": {
        "required_acts": ["армирование", "опалубка", "бетонирование"],
        "required_journals": ["журнал бетонных работ", "журнал замоноличивания"],
        "required_schemes": ["схемы армирования", "геодезические схемы"],
        "required_passports": ["арматура", "бетон", "протоколы кубиков"],
    },
    "OV": {
        "required_acts": ["монтаж воздуховодов", "монтаж оборудования", "пусконаладка"],
        "required_journals": ["журнал монтажа систем вентиляции", "журнал испытаний ОВ"],
        "required_schemes": ["исполнительные схемы трасс ОВ", "аксонометрические схемы"],
        "required_passports": ["вентиляционное оборудование", "воздуховоды", "протоколы испытаний"],
    },
    "VK": {
        "required_acts": ["монтаж трубопроводов", "опрессовка", "гидравлические испытания"],
        "required_journals": ["журнал сварочных работ", "журнал испытаний ВК"],
        "required_schemes": ["исполнительные схемы сетей ВК", "геодезические схемы"],
        "required_passports": ["трубная продукция", "запорная арматура", "протоколы испытаний"],
    },
    "EM": {
        "required_acts": ["прокладка кабельных линий", "монтаж щитов", "пусконаладка"],
        "required_journals": ["журнал электромонтажных работ", "журнал испытаний ЭМ"],
        "required_schemes": ["исполнительные схемы кабельных трасс", "однолинейные схемы"],
        "required_passports": ["кабельная продукция", "щитовое оборудование", "протоколы измерений"],
    },
    "AR": {
        "required_acts": ["кирпичная кладка", "монтаж перегородок", "отделочные работы"],
        "required_journals": ["общий журнал работ", "журнал отделочных работ"],
        "required_schemes": ["исполнительные схемы этажей", "планы фактических отметок"],
        "required_passports": ["строительные смеси", "листовые материалы", "сертификаты соответствия"],
    },
    "SS": {
        "required_acts": ["монтаж кабельных линий", "монтаж оборудования", "пусконаладка"],
        "required_journals": ["журнал монтажа СС", "журнал испытаний СС"],
        "required_schemes": ["исполнительные схемы СС", "структурные схемы"],
        "required_passports": ["кабели связи", "оборудование СС", "протоколы тестирования"],
    },
    "APS": {
        "required_acts": ["монтаж извещателей", "монтаж шлейфов", "пусконаладка"],
        "required_journals": ["журнал монтажа АПС", "журнал испытаний АПС"],
        "required_schemes": ["исполнительные схемы АПС", "планы размещения извещателей"],
        "required_passports": ["извещатели", "приборы ППК", "протоколы испытаний"],
    },
    "PS": {
        "required_acts": ["монтаж спринклерных линий", "монтаж насосной станции", "опрессовка"],
        "required_journals": ["журнал монтажа ПС", "журнал испытаний ПС"],
        "required_schemes": ["исполнительные схемы ПС", "гидравлические схемы"],
        "required_passports": ["трубопроводы", "пожарная арматура", "протоколы испытаний"],
    },
}


_REQUIREMENT_KEYS = (
    ("required_acts", "act"),
    ("required_journals", "journal"),
    ("required_schemes", "scheme"),
    ("required_passports", "passport"),
)


class GSNReadinessChecker:
    """Check project document readiness for GSN handover checklist."""

    def __init__(self) -> None:
        self._sessionmaker = get_projects_sessionmaker(settings.sqlite_db_path)

    def _list_section_documents(self, project_id: str, section: str) -> list[ProjectDocument]:
        with self._sessionmaker() as session:
            project_docs = (
                session.query(ProjectDocument)
                .filter(ProjectDocument.project_id == UUID(project_id))
                .order_by(ProjectDocument.created_at.asc())
                .all()
            )

        section_lower = section.lower()
        filtered = [
            doc
            for doc in project_docs
            if section_lower in (doc.document_type or "").lower()
            or section_lower in (doc.title or "").lower()
        ]
        return filtered

    @staticmethod
    def _matches_requirement(doc: ProjectDocument, requirement_name: str) -> bool:
        haystack = f"{doc.document_type} {doc.title}".lower()
        return requirement_name.lower() in haystack

    @staticmethod
    def _serialize_present(doc_type: str, name: str, doc_id: str) -> dict[str, str]:
        return {"type": doc_type, "name": name, "doc_id": doc_id}

    @staticmethod
    def _serialize_missing(doc_type: str, name: str) -> dict[str, str]:
        return {"type": doc_type, "name": name}

    @staticmethod
    def _completion_pct(present: Iterable[dict], total_required: int) -> float:
        if total_required <= 0:
            return 100.0
        ready_count = len(list(present))
        return round((ready_count / total_required) * 100, 2)

    async def check_section(self, project_id: str, section: str) -> dict:
        """
        Сверить наличие АОСР, журналов, исп. схем, паспортов с GSN_REQUIREMENTS.
        """
        normalized_section = section.upper()
        requirements = GSN_REQUIREMENTS.get(normalized_section)
        if requirements is None:
            raise ValueError(f"Unsupported section: {section}")

        docs = self._list_section_documents(project_id=project_id, section=normalized_section)

        missing: list[dict[str, str]] = []
        present: list[dict[str, str]] = []
        for requirement_key, requirement_type in _REQUIREMENT_KEYS:
            for name in requirements[requirement_key]:
                matched = next((doc for doc in docs if self._matches_requirement(doc, name)), None)
                if matched is None:
                    missing.append(self._serialize_missing(requirement_type, name))
                else:
                    present.append(
                        self._serialize_present(requirement_type, name, str(matched.id)),
                    )

        total_required = sum(len(requirements[key]) for key, _ in _REQUIREMENT_KEYS)
        completion_pct = self._completion_pct(present=present, total_required=total_required)

        return {
            "section": normalized_section,
            "ready": not missing,
            "missing": missing,
            "present": present,
            "completion_pct": completion_pct,
        }

    async def check_full_project(self, project_id: str) -> dict:
        """Проверить все разделы, вернуть сводный чеклист."""
        sections = []
        for section in GSN_REQUIREMENTS:
            sections.append(await self.check_section(project_id=project_id, section=section))

        avg_completion = 0.0
        if sections:
            avg_completion = round(sum(item["completion_pct"] for item in sections) / len(sections), 2)

        return {
            "project_id": project_id,
            "ready": all(item["ready"] for item in sections),
            "completion_pct": avg_completion,
            "sections": sections,
        }
