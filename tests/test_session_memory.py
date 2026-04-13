"""Тесты SessionMemory."""

from core.session_memory import SessionMemory


def test_session_memory_fifo_limit() -> None:
    """При переполнении хранилища старые сообщения удаляются по FIFO."""
    memory = SessionMemory(max_messages=50)
    session_id = "s-fifo"

    for idx in range(55):
        memory.add(session_id, role="user", content=f"msg-{idx}")

    history = memory.get(session_id, last_n=100)
    assert len(history) == 50
    assert history[0]["content"] == "msg-5"
    assert history[-1]["content"] == "msg-54"


def test_session_memory_get_last_n() -> None:
    """get(last_n) должен возвращать только последние N сообщений."""
    memory = SessionMemory()
    session_id = "s-last-n"

    for idx in range(6):
        memory.add(session_id, role="assistant", content=f"reply-{idx}")

    history = memory.get(session_id, last_n=3)
    assert [item["content"] for item in history] == ["reply-3", "reply-4", "reply-5"]


def test_session_memory_clear() -> None:
    """clear должен удалять историю сессии."""
    memory = SessionMemory()
    session_id = "s-clear"

    memory.add(session_id, role="agent", content="internal-note")
    assert len(memory.get(session_id)) == 1

    memory.clear(session_id)
    assert memory.get(session_id) == []
