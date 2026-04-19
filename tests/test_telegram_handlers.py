"""Тесты Telegram хэндлеров."""

import asyncio
import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _install_aiogram_stubs() -> None:
    """Устанавливает стабы aiogram для тестирования без реального пакета."""
    if "aiogram" in sys.modules:
        return

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
    aiogram.BaseMiddleware = object

    filters = types.ModuleType("aiogram.filters")
    filters.Command = lambda value: value

    fsm_context = types.ModuleType("aiogram.fsm.context")
    fsm_context.FSMContext = object

    fsm_state = types.ModuleType("aiogram.fsm.state")

    class _State:
        def __init__(self, *args, **kwargs):
            pass

    class _StatesGroupMeta(type):
        def __new__(mcs, name, bases, namespace):
            cls = super().__new__(mcs, name, bases, namespace)
            for key, val in namespace.items():
                if isinstance(val, _State):
                    setattr(cls, key, f"{name}:{key}")
            return cls

    class _StatesGroup(metaclass=_StatesGroupMeta):
        pass

    fsm_state.State = _State
    fsm_state.StatesGroup = _StatesGroup

    types_mod = types.ModuleType("aiogram.types")
    types_mod.BufferedInputFile = object
    types_mod.CallbackQuery = object
    types_mod.Message = object
    types_mod.ReplyKeyboardRemove = lambda **kw: None

    class _InlineKeyboardButton:
        def __init__(self, *, text="", callback_data=""):
            self.text = text
            self.callback_data = callback_data

    class _InlineKeyboardMarkup:
        def __init__(self, *, inline_keyboard=None):
            self.inline_keyboard = inline_keyboard or []

    class _KeyboardButton:
        def __init__(self, *, text=""):
            self.text = text

    class _ReplyKeyboardMarkup:
        def __init__(self, *, keyboard=None, resize_keyboard=False, one_time_keyboard=False):
            self.keyboard = keyboard or []
            self.resize_keyboard = resize_keyboard
            self.one_time_keyboard = one_time_keyboard

    types_mod.InlineKeyboardButton = _InlineKeyboardButton
    types_mod.InlineKeyboardMarkup = _InlineKeyboardMarkup
    types_mod.KeyboardButton = _KeyboardButton
    types_mod.ReplyKeyboardMarkup = _ReplyKeyboardMarkup
    types_mod.Document = object
    types_mod.WebAppInfo = lambda url="": SimpleNamespace(url=url)

    sys.modules["aiogram"] = aiogram
    sys.modules["aiogram.filters"] = filters
    sys.modules["aiogram.fsm.context"] = fsm_context
    sys.modules["aiogram.fsm.state"] = fsm_state
    sys.modules["aiogram.types"] = types_mod
    sys.modules["aiogram.enums"] = types.ModuleType("aiogram.enums")
    sys.modules["aiogram.client"] = types.ModuleType("aiogram.client")
    sys.modules["aiogram.client.default"] = types.ModuleType("aiogram.client.default")


def _reload_modules():
    """Перезагружает модули telegram для получения свежих определений."""
    for mod_name in list(sys.modules):
        if mod_name.startswith("telegram."):
            del sys.modules[mod_name]
    states = importlib.import_module("telegram.states")
    keyboards = importlib.import_module("telegram.keyboards")
    handlers = importlib.import_module("telegram.handlers")
    return states, keyboards, handlers


def _make_fsm_state():
    """Создаёт мок FSMContext."""
    data = {}

    async def update_data(**kwargs):
        data.update(kwargs)

    async def get_data():
        return dict(data)

    state = SimpleNamespace(
        set_state=AsyncMock(),
        update_data=AsyncMock(side_effect=update_data),
        get_data=AsyncMock(side_effect=get_data),
        clear=AsyncMock(),
    )
    state._data = data
    return state


# ── Существующие тесты ────────────────────────────────────────────────────────


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


# ── Новые тесты FSM-диалогов ─────────────────────────────────────────────────


def test_tk_volume_validation_rejects_non_number():
    """Валидация объёма: нечисловое значение отклоняется."""
    _install_aiogram_stubs()
    _reload_modules()
    handlers = importlib.import_module("telegram.handlers")

    state = _make_fsm_state()
    message = SimpleNamespace(
        text="не число",
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
    )

    asyncio.run(handlers.tk_volume_handler(message, state))

    message.answer.assert_awaited_once_with("Введите корректное число для объёма.")
    state.set_state.assert_not_awaited()


def test_ks_period_validation_rejects_bad_format():
    """Валидация периода КС: некорректный формат отклоняется."""
    _install_aiogram_stubs()
    _reload_modules()
    handlers = importlib.import_module("telegram.handlers")

    state = _make_fsm_state()
    message = SimpleNamespace(
        text="2024-01-01 - 2024-02-01",
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
    )

    asyncio.run(handlers.ks_period_handler(message, state))

    message.answer.assert_awaited_once()
    call_text = message.answer.await_args.args[0]
    assert "формат" in call_text.lower() or "неверн" in call_text.lower()
    state.set_state.assert_not_awaited()


def test_letter_body_points_accumulates_theses():
    """Тезисы письма накапливаются по одному."""
    _install_aiogram_stubs()
    _reload_modules()
    handlers = importlib.import_module("telegram.handlers")

    state = _make_fsm_state()

    # Первый тезис
    msg1 = SimpleNamespace(
        text="Тезис 1",
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
    )
    asyncio.run(handlers.letter_body_points_handler(msg1, state))

    assert state._data["body_points"] == ["Тезис 1"]

    # Второй тезис
    msg2 = SimpleNamespace(
        text="Тезис 2",
        from_user=SimpleNamespace(id=1),
        answer=AsyncMock(),
    )
    asyncio.run(handlers.letter_body_points_handler(msg2, state))

    assert state._data["body_points"] == ["Тезис 1", "Тезис 2"]


def test_keyboards_have_correct_structure():
    """Клавиатуры имеют правильную структуру."""
    _install_aiogram_stubs()
    _reload_modules()
    keyboards = importlib.import_module("telegram.keyboards")

    # unit_keyboard: 6 единиц
    uk = keyboards.unit_keyboard()
    unit_buttons = [row[0] for row in uk.inline_keyboard]
    unit_texts = [b.text for b in unit_buttons]
    assert len(unit_texts) == 6
    assert "м³" in unit_texts
    assert "м²" in unit_texts
    assert "шт." in unit_texts

    # letter_type_keyboard: 4 типа
    lt = keyboards.letter_type_keyboard()
    lt_buttons = [row[0] for row in lt.inline_keyboard]
    lt_texts = [b.text for b in lt_buttons]
    assert len(lt_texts) == 4
    assert "Запрос" in lt_texts
    assert "Претензия" in lt_texts

    # confirm_keyboard: 2 кнопки в одном ряду
    ck = keyboards.confirm_keyboard()
    assert len(ck.inline_keyboard) == 1
    row = ck.inline_keyboard[0]
    assert len(row) == 2
    assert row[0].callback_data == "confirm:yes"
    assert row[1].callback_data == "confirm:no"

    # skip_keyboard: Пропустить и Отмена
    sk = keyboards.skip_keyboard()
    skip_texts = [b.text for b in sk.keyboard[0]]
    assert "Пропустить" in skip_texts
    assert "Отмена" in skip_texts


def test_projects_handler_continues_when_documents_request_fails(monkeypatch):
    _install_aiogram_stubs()
    handlers = importlib.import_module("telegram.handlers")
    handlers.project_doc_tokens.clear()

    async def _fake_get(path: str):
        if path == "/api/projects":
            return {"projects": [{"id": "project-1", "name": "Test project"}]}
        raise handlers.httpx.HTTPStatusError(
            "boom",
            request=SimpleNamespace(url=path),
            response=SimpleNamespace(status_code=500),
        )

    monkeypatch.setattr(handlers.api_client, "get", _fake_get)

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=777),
        answer=AsyncMock(),
    )

    asyncio.run(handlers.projects_handler(message))

    message.answer.assert_awaited_once()
    text = message.answer.await_args.args[0]
    assert "Test project" in text
    assert "Документы временно недоступны" in text


def test_project_doc_callback_uses_short_token_mapping():
    _install_aiogram_stubs()
    handlers = importlib.import_module("telegram.handlers")
    handlers.project_doc_tokens.clear()
    handlers.Message = object

    token = handlers._store_project_doc_token(10, "very-long-session-id-value")

    callback = SimpleNamespace(
        data=f"project_doc:{token}",
        from_user=SimpleNamespace(id=10),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )

    asyncio.run(handlers.project_doc_callback_handler(callback))

    callback.message.answer.assert_awaited_once_with(
        "Откройте документ в сессии: very-long-session-id-value",
    )
    callback.answer.assert_awaited_once()


def test_link_invalid_key_format_returns_message():
    _install_aiogram_stubs()
    handlers = importlib.import_module("telegram.handlers")
    message = SimpleNamespace(
        text="/link bad!",
        from_user=SimpleNamespace(id=55),
        answer=AsyncMock(),
    )

    asyncio.run(handlers.link_handler(message))

    message.answer.assert_awaited_once_with("Неверный формат ключа")


def test_rate_limit_blocks_11th_request(monkeypatch):
    module = importlib.import_module("telegram.middlewares.rate_limit")

    class FakeRedis:
        def __init__(self):
            self.counter = 0

        async def incr(self, _key):
            self.counter += 1
            return self.counter

        async def expire(self, _key, _seconds):
            return True

        async def ttl(self, _key):
            return 42

        async def close(self):
            return None

    fake = FakeRedis()
    monkeypatch.setattr(module, "_redis_client", lambda: fake)

    async def _run():
        for _ in range(10):
            allowed, retry_after = await module.check_rate_limit(77)
            assert allowed is True
            assert retry_after == 0

        allowed, retry_after = await module.check_rate_limit(77)
        assert allowed is False
        assert retry_after == 42

    asyncio.run(_run())
