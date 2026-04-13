"""Тесты SessionMemory c SQLite backend."""

from __future__ import annotations

import aiosqlite
import pytest

from core.database import init_db
from core.session_memory import SessionMemory


@pytest.fixture
async def memory() -> SessionMemory:
    """SessionMemory на in-memory SQLite (shared cache)."""
    db_path = "file::memory:?cache=shared"
    keeper = await aiosqlite.connect(db_path, uri=True)
    try:
        await init_db(db_path)
        yield SessionMemory(max_messages=50, db_path=db_path)
    finally:
        await keeper.close()


@pytest.mark.asyncio
async def test_session_memory_fifo_limit(memory: SessionMemory) -> None:
    """При переполнении хранилища старые сообщения удаляются по FIFO."""
    session_id = "s-fifo"

    for idx in range(55):
        await memory.add(session_id, role="user", content=f"msg-{idx}")

    history = await memory.get(session_id, last_n=100)
    assert len(history) == 50
    assert history[0]["content"] == "msg-5"
    assert history[-1]["content"] == "msg-54"


@pytest.mark.asyncio
async def test_session_memory_get_last_n(memory: SessionMemory) -> None:
    """get(last_n) должен возвращать только последние N сообщений."""
    session_id = "s-last-n"

    for idx in range(6):
        await memory.add(session_id, role="assistant", content=f"reply-{idx}")

    history = await memory.get(session_id, last_n=3)
    assert [item["content"] for item in history] == ["reply-3", "reply-4", "reply-5"]


@pytest.mark.asyncio
async def test_session_memory_clear(memory: SessionMemory) -> None:
    """clear должен удалять историю сессии."""
    session_id = "s-clear"

    await memory.add(session_id, role="agent", content="internal-note")
    assert len(await memory.get(session_id)) == 1

    await memory.clear(session_id)
    assert await memory.get(session_id) == []


@pytest.mark.asyncio
async def test_session_memory_documents(memory: SessionMemory) -> None:
    """save_document/get_session_documents должны работать через SQLite."""
    session_id = "s-docs"
    payload = b"docx-content"

    await memory.save_document(
        session_id=session_id,
        doc_type="tk",
        filename="tk_s-docs.docx",
        docx_bytes=payload,
        sha256="abc123",
    )

    docs = await memory.get_session_documents(session_id)
    assert len(docs) == 1
    assert docs[0]["doc_type"] == "tk"
    assert docs[0]["docx_bytes"] == payload
    assert docs[0]["sha256"] == "abc123"
