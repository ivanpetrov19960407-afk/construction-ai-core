from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from core.pipelines.chat_rag import ChatRagPipeline


class _FakeCollection:
    def __init__(self):
        self.user_docs = [
            {
                "text": "СП 48.13330 устанавливает требования к организации строительства.",
                "source": "sp_48.pdf",
                "page": 2,
                "username": "user-1",
            }
        ]
        self.global_docs = [
            {
                "text": "ГОСТ Р 21.1101 описывает требования к проектной документации.",
                "source": "gost_21.pdf",
                "page": 7,
                "username": "",
            }
        ]

    def get(self, where=None, include=None):
        _ = include
        if where == {"username": "user-1"}:
            return {"metadatas": [{"username": "user-1"}]}
        return {"metadatas": []}

    def query(self, query_embeddings=None, n_results=6, include=None, where=None):
        _ = query_embeddings, include
        rows = self.user_docs if where == {"username": "user-1"} else self.global_docs
        rows = rows[:n_results]
        metadatas = [
            {
                "source": row["source"],
                "page": row["page"],
                "username": row["username"],
            }
            for row in rows
        ]
        return {
            "documents": [[row["text"] for row in rows]],
            "metadatas": [metadatas],
            "distances": [[0.1 for _ in rows]],
        }


class _FakeRagEngine:
    def __init__(self):
        self.collection = _FakeCollection()

    def _embed_texts(self, texts):
        _ = texts
        return [[0.01, 0.02, 0.03]]


def test_chat_rag_prefers_personal_sources():
    llm_router = SimpleNamespace(query=AsyncMock(return_value=SimpleNamespace(text="Ответ [S1]")))
    pipeline = ChatRagPipeline(rag_engine=_FakeRagEngine(), llm_router=llm_router)

    result = asyncio.run(
        pipeline.run(
            message="Что такое СП 48.13330?",
            user_id="user-1",
            role_system_prompt="role prompt",
            top_k=6,
        )
    )

    assert result["agents_used"] == ["retriever", "responder"]
    assert result["sources"]
    assert result["sources"][0]["title"] == "sp_48.pdf"


def test_chat_rag_falls_back_to_global_when_personal_empty():
    llm_router = SimpleNamespace(query=AsyncMock(return_value=SimpleNamespace(text="Ответ [S1]")))
    pipeline = ChatRagPipeline(rag_engine=_FakeRagEngine(), llm_router=llm_router)

    result = asyncio.run(
        pipeline.run(
            message="Что такое ГОСТ?",
            user_id="unknown-user",
            role_system_prompt="role prompt",
            top_k=6,
        )
    )

    assert result["sources"][0]["title"] == "gost_21.pdf"
