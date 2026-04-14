"""Тесты SessionMemory c SQLite backend."""

from __future__ import annotations

import asyncio

import pytest

from core.database import init_db
from core.session_memory import SessionMemory


@pytest.fixture
def memory(tmp_path: pytest.TempPathFactory) -> SessionMemory:
    """SessionMemory на временном SQLite-файле."""
    db_path = str(tmp_path / "session_memory.db")
    asyncio.run(init_db(db_path))
    return SessionMemory(max_messages=50, db_path=db_path)


def test_session_memory_fifo_limit(memory: SessionMemory) -> None:
    """При переполнении хранилища старые сообщения удаляются по FIFO."""
    session_id = "s-fifo"

    for idx in range(55):
        asyncio.run(memory.add(session_id, role="user", content=f"msg-{idx}"))

    history = asyncio.run(memory.get(session_id, last_n=100))
    assert len(history) == 50
    assert history[0]["content"] == "msg-5"
    assert history[-1]["content"] == "msg-54"


def test_session_memory_get_last_n(memory: SessionMemory) -> None:
    """get(last_n) должен возвращать только последние N сообщений."""
    session_id = "s-last-n"

    for idx in range(6):
        asyncio.run(memory.add(session_id, role="assistant", content=f"reply-{idx}"))

    history = asyncio.run(memory.get(session_id, last_n=3))
    assert [item["content"] for item in history] == ["reply-3", "reply-4", "reply-5"]


def test_session_memory_clear(memory: SessionMemory) -> None:
    """clear должен удалять историю сессии."""
    session_id = "s-clear"

    asyncio.run(memory.add(session_id, role="agent", content="internal-note"))
    assert len(asyncio.run(memory.get(session_id))) == 1

    asyncio.run(memory.clear(session_id))
    assert asyncio.run(memory.get(session_id)) == []


def test_session_memory_documents(memory: SessionMemory) -> None:
    """save_document/get_session_documents должны работать через SQLite."""
    session_id = "s-docs"
    payload = b"docx-content"

    asyncio.run(
        memory.save_document(
            session_id=session_id,
            doc_type="tk",
            filename="tk_s-docs.docx",
            docx_bytes=payload,
            sha256="abc123",
        )
    )

    docs = asyncio.run(memory.get_session_documents(session_id))
    assert len(docs) == 1
    assert docs[0]["doc_type"] == "tk"
    assert docs[0]["docx_bytes"] == payload
    assert docs[0]["sha256"] == "abc123"
