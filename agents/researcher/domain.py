from __future__ import annotations

from schemas.research import Diagnostic, ResearchSource

_NORM_HINTS = ("сп", "гост", "снип", "санпин", "фз", "приказ")
_LAW_HINTS = ("федеральный закон", "кодекс", "постановление")
_PROJECT_HINTS = ("проект", "рабочая документация", "рд", "пд")


def classify_source_type(source: ResearchSource) -> str:
    raw = " ".join(
        [
            source.source_type or "",
            source.type or "",
            source.title or "",
            source.document or "",
            source.authority or "",
        ]
    ).lower()
    if any(h in raw for h in _NORM_HINTS):
        return "norm"
    if any(h in raw for h in _LAW_HINTS):
        return "law"
    if any(h in raw for h in _PROJECT_HINTS):
        return "project_doc"
    if source.type == "web" or source.url:
        return "web"
    return "unknown"


def is_normative_source(source: ResearchSource) -> bool:
    return classify_source_type(source) in {"norm", "law"}


def is_active_source(source: ResearchSource) -> bool:
    if source.is_active is None:
        return True
    return bool(source.is_active)


def detect_version_conflict(sources: list[ResearchSource]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    by_doc: dict[str, list[ResearchSource]] = {}
    for source in sources:
        doc = (source.document or source.title or "").strip().lower()
        if not doc:
            continue
        by_doc.setdefault(doc, []).append(source)

    for group in by_doc.values():
        versions = {s.document_version for s in group if s.document_version}
        if len(versions) > 1:
            diagnostics.append(
                Diagnostic(
                    code="source_version_conflict",
                    message=f"version conflict: {sorted(versions)}",
                    severity="warn",
                    component="domain",
                    stage="domain",
                )
            )
    return diagnostics


def choose_primary_sources(query: str, sources: list[ResearchSource]) -> list[ResearchSource]:
    q = query.lower()
    project_specific = any(x in q for x in ("по проекту", "проект-specific", "для проекта"))
    prefer_normative = any(x in q for x in ("актуальная норма", "действующий сп", "по гост"))

    def rank(source: ResearchSource) -> tuple[int, int, float]:
        src_type = classify_source_type(source)
        base = {"law": 4, "norm": 3, "project_doc": 2, "web": 1, "unknown": 0}[src_type]
        if project_specific and src_type == "project_doc":
            base = 5
        if prefer_normative and src_type in {"law", "norm"}:
            base += 2
        if not project_specific and src_type == "project_doc":
            base -= 1
        active = 1 if is_active_source(source) else 0
        return (base, active, source.score)

    return sorted(sources, key=rank, reverse=True)


def diagnostics_for_sources(sources: list[ResearchSource]) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(detect_version_conflict(sources))
    for source in sources:
        if is_normative_source(source) and not source.jurisdiction:
            diagnostics.append(
                Diagnostic(
                    code="source_missing_jurisdiction",
                    message=f"source {source.id} missing jurisdiction",
                    severity="warn",
                    component="domain",
                    stage="domain",
                    source_id=source.id,
                )
            )
        if not is_active_source(source):
            diagnostics.append(
                Diagnostic(
                    code="source_inactive",
                    message=f"source {source.id} is inactive",
                    severity="warn",
                    component="domain",
                    stage="domain",
                    source_id=source.id,
                )
            )
    return diagnostics
