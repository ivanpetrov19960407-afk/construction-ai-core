"""Тесты Telegram хэндлеров."""

import asyncio
import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _install_aiogram_stubs() -> None:
    aiogram = types.ModuleType("aiogram")

    class DummyRouter:
        def message(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

        def callback_query(self, *args, **kwargs):
            def decorator(fn):
                return fn

            return decorator

    class DummyF:
        def __getattr__(self, _name):
            return self

        def startswith(self, *_args, **_kwargs):
            return self

        def casefold(self):
            return self

        def __eq__(self, _other):
            return self

    aiogram.F = DummyF()
    aiogram.Router = DummyRouter

    filters = types.ModuleType("aiogram.filters")
    filters.Command = lambda value: value

    fsm_context = types.ModuleType("aiogram.fsm.context")
    fsm_context.FSMContext = object

    fsm_state = types.ModuleType("aiogram.fsm.state")
    fsm_state.State = object
    fsm_state.StatesGroup = object

    types_mod = types.ModuleType("aiogram.types")
    types_mod.BufferedInputFile = object
    types_mod.CallbackQuery = object
    types_mod.Message = object
    types_mod.ReplyKeyboardRemove = object
    types_mod.InlineKeyboardButton = object
    types_mod.InlineKeyboardMarkup = object
    types_mod.KeyboardButton = object
    types_mod.ReplyKeyboardMarkup = object
    types_mod.Document = object

    sys.modules["aiogram"] = aiogram
    sys.modules["aiogram.filters"] = filters
    sys.modules["aiogram.fsm.context"] = fsm_context
    sys.modules["aiogram.fsm.state"] = fsm_state
    sys.modules["aiogram.types"] = types_mod


def test_text_handler_calls_chat_endpoint(monkeypatch):
    _install_aiogram_stubs()

    handlers = importlib.import_module("telegram.handlers")

    post_mock = AsyncMock(return_value={"reply": "ok"})
    monkeypatch.setattr(handlers.api_client, "post", post_mock)
    handlers.user_roles[42] = "foreman"

    message = SimpleNamespace(
        text="Привет",
        from_user=SimpleNamespace(id=42),
        answer=AsyncMock(),
    )

    asyncio.run(handlers.text_message_handler(message))

    post_mock.assert_awaited_once_with(
        "/api/chat",
        {
            "message": "Привет",
            "session_id": "42",
            "role": "foreman",
        },
    )
    message.answer.assert_awaited_once_with("ok")


def test_analyze_document_downloads_and_posts(monkeypatch):
    _install_aiogram_stubs()

    handlers = importlib.import_module("telegram.handlers")

    analyze_mock = AsyncMock(
        return_value={
            "risks": ["Риск 1"],
            "mismatches": ["Несоответствие 1"],
            "recommendation": "УЧАСТВОВАТЬ",
            "confidence": 0.84,
        }
    )
    monkeypatch.setattr(handlers, "_analyze_tender_pdf", analyze_mock)
    state = SimpleNamespace(clear=AsyncMock())

    document = SimpleNamespace(file_size=1024, mime_type="application/pdf", file_name="tender.pdf")
    bot = SimpleNamespace(download=AsyncMock())
    message = SimpleNamespace(
        document=document,
        bot=bot,
        answer=AsyncMock(),
    )

    asyncio.run(handlers.analyze_document_handler(message, state))

    bot.download.assert_awaited_once()
    analyze_mock.assert_awaited_once()
    state.clear.assert_awaited_once()
    assert message.answer.await_count == 1


def test_analyze_helper_posts_to_tender_endpoint(monkeypatch):
    _install_aiogram_stubs()
    handlers = importlib.import_module("telegram.handlers")

    response = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"ok": True},
    )
    post_mock = AsyncMock(return_value=response)

    class DummyAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return SimpleNamespace(post=post_mock)

        async def __aexit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(handlers.httpx, "AsyncClient", DummyAsyncClient)

    asyncio.run(handlers._analyze_tender_pdf("x.pdf", b"123"))

    post_mock.assert_awaited_once()
    called_url = post_mock.await_args.args[0]
    assert called_url.endswith("/api/analyze/tender")
