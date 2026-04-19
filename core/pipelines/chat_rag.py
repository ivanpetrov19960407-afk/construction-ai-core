from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from core.rag_engine import RAGEngine


class ChatRagPipeline:
    """Базовый RAG pipeline для chat intent."""

    def __init__(self, rag_engine: RAGEngine, llm_router: Any):
        self.rag_engine = rag_engine
        self.llm_router = llm_router

    def _query(
        self,
        query: str,
        n_results: int,
        where: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        embedding = self.rag_engine._embed_texts([query])[0]
        query_embeddings: list[Sequence[float]] = [cast(Sequence[float], embedding)]
        payload = cast(
            Any,
            self.rag_engine.collection.query(
                query_embeddings=query_embeddings,
                n_results=n_results,
                include=["documents", "metadatas", "distances"],
                where=where,
            ),
        )
        documents = cast(list[list[str]], payload.get("documents") or [[]])
        metadatas = cast(list[list[dict[str, Any]]], payload.get("metadatas") or [[]])
        distances = cast(list[list[float]], payload.get("distances") or [[]])

        rows: list[dict[str, Any]] = []
        for text, meta, distance in zip(documents[0], metadatas[0], distances[0], strict=False):
            metadata = meta or {}
            rows.append(
                {
                    "text": text,
                    "source": str(metadata.get("source", "unknown")),
                    "page": int(metadata.get("page", 0) or 0),
                    "score": max(0.0, 1.0 - float(distance)),
                    "username": str(metadata.get("username", "") or ""),
                }
            )
        return rows

    def _has_personal_sources(self, user_id: str) -> bool:
        payload = cast(
            Any,
            self.rag_engine.collection.get(
                where={"username": user_id},
                include=["metadatas"],
            ),
        )
        metadatas = payload.get("metadatas") or []
        return bool(metadatas)

    @staticmethod
    def _context_block(chunks: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for idx, chunk in enumerate(chunks, start=1):
            source = chunk["source"]
            page = chunk["page"]
            score = chunk["score"]
            text = chunk["text"]
            lines.append(f"[S{idx}] {source} (стр. {page}, score={score:.3f}):\n{text}")
        return "\n\n".join(lines)

    @staticmethod
    def _to_sources(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "title": str(chunk.get("source", "unknown")),
                "page": int(chunk.get("page", 0) or 0),
                "score": round(float(chunk.get("score", 0.0)), 4),
            }
            for chunk in chunks
        ]

    def _query_global(self, message: str, top_k: int) -> list[dict[str, Any]]:
        """Find top_k global chunks even when personal docs dominate nearest neighbors."""
        requested = max(top_k * 2, 12)
        max_requested = 120

        while True:
            candidates = self._query(message, n_results=requested, where=None)
            global_only = [item for item in candidates if not item.get("username")]
            if len(global_only) >= top_k or requested >= max_requested:
                return global_only[:top_k]
            requested = min(max_requested, requested * 2)

    async def run(
        self,
        *,
        message: str,
        user_id: str,
        role_system_prompt: str,
        top_k: int = 6,
    ) -> dict[str, Any]:
        steps = ["retriever"]
        chunks: list[dict[str, Any]] = []

        if self._has_personal_sources(user_id):
            chunks = self._query(message, n_results=top_k, where={"username": user_id})

        if not chunks:
            # fallback на глобальную базу (документы без username)
            chunks = self._query_global(message, top_k=top_k)

        context_block = self._context_block(chunks[:top_k]) if chunks else ""
        system_prompt = role_system_prompt
        if context_block:
            system_prompt = (
                f"{role_system_prompt}\n\n"
                "Используй только подтверждаемые фрагменты из базы знаний ниже. "
                "Если ответа нет в источниках — так и скажи. Ссылайся в формате [S1], [S2].\n\n"
                f"Контекст:\n{context_block}"
            )

        llm_response = await self.llm_router.query(prompt=message, system_prompt=system_prompt)
        steps.append("responder")

        return {
            "reply": llm_response.text,
            "agents_used": steps,
            "sources": self._to_sources(chunks[:top_k]),
        }
