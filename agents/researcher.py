"""Агент Researcher — поиск информации по нормативам, вебу и базе знаний."""

from __future__ import annotations

import json
import logging
from typing import Any

from agents.base import BaseAgent
from core.llm_router import LLMRouter
from core.rag_engine import RAGEngine
from core.tools.web_search import WebSearchTool
from schemas.research import ResearchFact, ResearchResponse, ResearchSource

logger = logging.getLogger(__name__)


class RAGSearchTool:
    """Лёгкий tool-адаптер поверх RAGEngine."""

    def __init__(self, rag_engine: RAGEngine) -> None:
        self.rag_engine = rag_engine

    async def run(
        self,
        query: str,
        *,
        scope: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        chunks = await self.rag_engine.search(query, n_results=limit, filter_scope=scope)
        if scope and not chunks:
            chunks = await self.rag_engine.search(query, n_results=limit)
        return chunks or []


class ResearcherAgent(BaseAgent):
    """🔍 Researcher — универсальный поиск фактов с источниками и confidence."""

    system_prompt = (
        "Ты — Researcher агент. Анализируй предоставленные источники (RAG + web) "
        "и извлекай из них факты. Возвращай СТРОГО валидный JSON без markdown-обёртки "
        "по схеме:\n"
        '{"facts":[{"text":"...","applicability":"...",'
        '"confidence":0.0,"source_ids":["rag-0","web-1"]}],'
        '"gaps":["что не удалось найти"]}\n'
        "Правила:\n"
        "- Каждый факт должен ссылаться хотя бы на один source_id из списка источников.\n"
        "- confidence от 0.0 до 1.0, чем надёжнее источник — тем выше.\n"
        "- Если релевантных данных нет — верни facts:[] и опиши пробел в gaps.\n"
        "- Для строительных тем указывай номер документа и пункт в поле text."
    )

    def __init__(
        self,
        llm_router: LLMRouter,
        rag_engine: RAGEngine | None = None,
        web_search_tool: WebSearchTool | None = None,
    ) -> None:
        super().__init__(agent_id="01", llm_router=llm_router)
        self.rag_engine = rag_engine
        self.web_search_tool = web_search_tool or WebSearchTool()

    async def _run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Режим внутри pipeline — вызывается оркестратором."""
        if self.rag_engine is None:
            self.rag_engine = RAGEngine()

        message = str(state.get("message", "")).strip()
        scope = str(state.get("scope") or state.get("role") or "").strip() or None
        context = str(state.get("context", "")).strip()

        all_sources = await self._collect_sources(message, scope)
        prompt = self._build_research_prompt(message, context, all_sources)

        response = await self.llm_router.query(prompt=prompt, system_prompt=self.system_prompt)
        payload = self._parse_llm_json(message, response.text, all_sources)

        state["research_facts"] = response.text
        state["research_payload"] = payload.model_dump()
        return self._update_state(state, response.text)

    async def run_standalone(
        self,
        message: str,
        *,
        scope: str | None = None,
        context: str = "",
        user_id: str | None = None,
    ) -> ResearchResponse:
        """Соло-вызов без pipeline — для REST API и Telegram-бота."""
        state: dict[str, Any] = {
            "message": message,
            "scope": scope,
            "context": context,
            "user_id": user_id,
            "history": [],
        }
        result = await self.run(state)
        return ResearchResponse.model_validate(result["research_payload"])

    async def _collect_sources(self, message: str, scope: str | None) -> list[ResearchSource]:
        """Собрать источники из RAG и (если надо) из веба."""
        rag_tool = RAGSearchTool(self.rag_engine)  # type: ignore[arg-type]
        try:
            rag_chunks = await rag_tool.run(message, scope=scope)
        except Exception as exc:
            logger.warning("researcher.rag_failed: %s", exc)
            rag_chunks = []

        rag_sources = [self._rag_chunk_to_source(idx, chunk) for idx, chunk in enumerate(rag_chunks)]

        if self._need_web_fallback(rag_sources):
            try:
                web_items = await self.web_search_tool.run(message, max_results=5)
            except Exception as exc:
                logger.warning("researcher.web_failed: %s", exc)
                web_items = []
        else:
            web_items = []

        web_sources = [
            self._web_item_to_source(idx, item)
            for idx, item in enumerate(web_items, start=len(rag_sources))
        ]
        return [*rag_sources, *web_sources]

    def _need_web_fallback(self, rag_sources: list[ResearchSource]) -> bool:
        """Нужно ли подключать web search: мало источников или слабый avg score."""
        if len(rag_sources) < 2:
            return True
        return self._avg_score(rag_sources) < 0.35

    def _build_research_prompt(self, message: str, context: str, sources: list[ResearchSource]) -> str:
        chunks_text = "\n".join(self._source_brief(s) for s in sources) or "(релевантные источники не найдены)"
        prompt = f"Источники:\n{chunks_text}\n\nЗапрос пользователя: {message}"
        if context:
            prompt = f"Контекст:\n{context}\n\n{prompt}"
        return prompt

    def _source_brief(self, source: ResearchSource) -> str:
        if source.type == "rag":
            locator = source.locator or "без страницы"
            return f"- [{source.id} | {source.document or source.title}, {locator}] {source.snippet or ''}"
        return f"- [{source.id} | {source.title}] {source.snippet or source.url or ''}"

    def _parse_llm_json(
        self,
        query: str,
        raw: str,
        sources: list[ResearchSource],
    ) -> ResearchResponse:
        """Извлечь JSON из ответа LLM с graceful fallback."""
        facts: list[ResearchFact] = []
        gaps: list[str] = []

        try:
            data = json.loads(self._strip_markdown_fence(raw))
            if not isinstance(data, dict):
                raise TypeError("LLM JSON payload must be an object")
            facts = [ResearchFact(**f) for f in data.get("facts", [])]
            gaps = [str(g) for g in data.get("gaps", [])]
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            logger.info("researcher.json_parse_failed: %s", exc)
            facts = [
                ResearchFact(
                    text=raw.strip(),
                    applicability="Не удалось распарсить JSON — вернён сырой ответ",
                    confidence=self._avg_score(sources),
                    source_ids=[s.id for s in sources[:3]],
                )
            ]
            gaps = ["LLM вернул ответ не в JSON-формате"]

        if not sources:
            gaps.append("Не найдено релевантных источников")

        return ResearchResponse(
            query=query,
            facts=facts,
            sources=sources,
            gaps=gaps,
            confidence_overall=round(self._avg_score(sources), 2),
        )

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        """Убрать markdown-обёртку ```json ... ``` если LLM её добавил."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        return cleaned.strip()

    def _rag_chunk_to_source(self, idx: int, chunk: dict[str, Any]) -> ResearchSource:
        source_name = str(chunk.get("source", "unknown"))
        page = self._safe_int(chunk.get("page"))
        return ResearchSource(
            id=f"rag-{idx}",
            type="rag",
            title=source_name,
            document=source_name,
            page=page if page > 0 else None,
            locator=f"стр. {page}" if page > 0 else None,
            snippet=str(chunk.get("text", ""))[:400],
            score=self._safe_float(chunk.get("score")),
        )

    def _web_item_to_source(self, idx: int, item: dict[str, Any]) -> ResearchSource:
        url = item.get("url")
        published = item.get("published_at")
        return ResearchSource(
            id=f"web-{idx}",
            type="web",
            title=str(item.get("title", "Web source")),
            url=str(url) if url else None,
            snippet=str(item.get("snippet", ""))[:400],
            score=self._safe_float(item.get("score")),
            published_at=str(published) if published else None,
        )

    @staticmethod
    def _avg_score(sources: list[ResearchSource]) -> float:
        if not sources:
            return 0.0
        total = sum(s.score for s in sources)
        return min(1.0, max(0.0, total / len(sources)))

    @staticmethod
    def _safe_int(value: Any, default: int = 0) -> int:
        try:
            return int(value) if value is not None else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value) if value is not None else default
        except (TypeError, ValueError):
            return default
