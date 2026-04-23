"""Агент Researcher — поиск информации по нормативам и базе знаний."""

from __future__ import annotations

from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter
from core.rag_engine import RAGEngine
from core.tools.web_search import WebSearchTool
from schemas.research import ResearchFact, ResearchResponse, ResearchSource


class RAGSearchTool:
    """Лёгкий tool-адаптер поверх RAGEngine."""

    def __init__(self, rag_engine: RAGEngine):
        self.rag_engine = rag_engine

    async def run(
        self,
        query: str,
        *,
        role: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        chunks = await self.rag_engine.search(query, n_results=limit, filter_scope=role)
        if role and not chunks:
            chunks = await self.rag_engine.search(query, n_results=limit)
        return chunks


class ResearcherAgent(BaseAgent):
    """🔍 Researcher — поиск по нормативам и возврат структурированных фактов."""

    system_prompt = (
        "Ты — Researcher агент. Ищи факты по СП/СНиП/ГОСТ и стройнормам. "
        "Возвращай структурированно: 1) факт, 2) источник (номер документа, пункт), "
        "3) применимость. Если данных нет — явно укажи это."
    )

    def __init__(self, llm_router: LLMRouter) -> None:
        super().__init__(agent_id="01", llm_router=llm_router)
        self.rag_engine: RAGEngine | None = None
        self.web_search_tool = WebSearchTool()

    async def _run(self, state: dict[str, Any]) -> dict[str, Any]:
        if self.rag_engine is None:
            self.rag_engine = RAGEngine()

        message = str(state.get("message", "")).strip()
        role = str(state.get("role", "")).strip() or None

        rag_tool = RAGSearchTool(self.rag_engine)
        rag_chunks = await rag_tool.run(message, role=role)
        rag_sources = [
            self._rag_chunk_to_source(index, chunk)
            for index, chunk in enumerate(rag_chunks)
        ]

        should_use_web = len(rag_sources) < 2 or self._avg_score(rag_sources) < 0.35
        web_items: list[dict[str, Any]] = []
        if should_use_web:
            web_items = await self.web_search_tool.run(message, max_results=5)
        web_sources = [
            self._web_item_to_source(index, item)
            for index, item in enumerate(web_items, start=len(rag_sources))
        ]

        all_sources = [*rag_sources, *web_sources]
        chunks_text = "\n".join(self._source_brief(source) for source in all_sources)
        if not chunks_text:
            chunks_text = "(релевантные источники не найдены)"

        rag_prompt = f"Источники:\n{chunks_text}\n\nЗапрос пользователя: {message}"
        context = str(state.get("context", ""))
        prompt = f"Контекст:\n{context}\n\n{rag_prompt}" if context else rag_prompt

        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)
        payload = self._build_research_payload(message, response.text, all_sources)

        state["research_facts"] = response.text
        state["research_payload"] = payload.model_dump()
        return self._update_state(state, response.text)

    def _build_research_payload(
        self,
        query: str,
        answer_text: str,
        sources: list[ResearchSource],
    ) -> ResearchResponse:
        source_ids = [source.id for source in sources][:3]
        fact = ResearchFact(
            text=answer_text.strip(),
            applicability="Уточняется по контексту запроса",
            confidence=round(self._avg_score(sources), 2),
            source_ids=source_ids,
        )
        gaps = [] if sources else ["Не найдено релевантных источников"]
        return ResearchResponse(
            query=query,
            facts=[fact],
            sources=sources,
            gaps=gaps,
            confidence_overall=round(self._avg_score(sources), 2),
        )

    def _avg_score(self, sources: list[ResearchSource]) -> float:
        if not sources:
            return 0.0
        total = sum(source.score for source in sources)
        return min(1.0, max(0.0, total / len(sources)))

    def _rag_chunk_to_source(self, idx: int, chunk: dict[str, Any]) -> ResearchSource:
        source = str(chunk.get("source", "unknown"))
        page = int(chunk.get("page", 0))
        return ResearchSource(
            id=f"rag-{idx}",
            type="rag",
            title=source,
            document=source,
            page=page if page > 0 else None,
            locator=f"стр. {page}" if page > 0 else None,
            snippet=str(chunk.get("text", ""))[:400],
            score=float(chunk.get("score", 0.0)),
        )

    def _web_item_to_source(self, idx: int, item: dict[str, Any]) -> ResearchSource:
        return ResearchSource(
            id=f"web-{idx}",
            type="web",
            title=str(item.get("title", "Web source")),
            url=str(item.get("url")) if item.get("url") else None,
            snippet=str(item.get("snippet", ""))[:400],
            score=float(item.get("score", 0.0)),
            published_at=str(item.get("published_at")) if item.get("published_at") else None,
        )

    def _source_brief(self, source: ResearchSource) -> str:
        if source.type == "rag":
            return (
                f"- [rag:{source.document or source.title}, {source.locator or 'без страницы'}] "
                f"{source.snippet or ''}"
            )
        return f"- [web:{source.title}] {source.snippet or source.url or ''}"
