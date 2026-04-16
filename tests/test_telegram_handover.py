"""Тесты handover-команд Telegram-бота."""

import asyncio
import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock


def _install_aiogram_stubs() -> None:
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

        def include_router(self, _router):
            return None

    class DummyF:
        def __getattr__(self, _name):
            return self

        def startswith(self, *_args, **_kwargs):
            return self

        def casefold(self):
            return self

        def __call__(self, *_args, **_kwargs):
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

    class _InlineKeyboardButton:
        def __init__(self, *, text="", callback_data="", web_app=None):
            self.text = text
            self.callback_data = callback_data
            self.web_app = web_app

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

    class _WebAppInfo:
        def __init__(self, *, url=""):
            self.url = url

    types_mod.InlineKeyboardButton = _InlineKeyboardButton
    types_mod.InlineKeyboardMarkup = _InlineKeyboardMarkup
    types_mod.KeyboardButton = _KeyboardButton
    types_mod.ReplyKeyboardMarkup = _ReplyKeyboardMarkup
    types_mod.WebAppInfo = _WebAppInfo
    types_mod.BufferedInputFile = object
    types_mod.CallbackQuery = object
    types_mod.Message = object
    types_mod.ReplyKeyboardRemove = lambda **kw: None
    types_mod.Document = object

    sys.modules["aiogram"] = aiogram
    sys.modules["aiogram.filters"] = filters
    sys.modules["aiogram.fsm.context"] = fsm_context
    sys.modules["aiogram.fsm.state"] = fsm_state
    sys.modules["aiogram.types"] = types_mod


def _reload_handover_module():
    for name in list(sys.modules):
        if name.startswith("telegram.handlers"):
            del sys.modules[name]
    importlib.import_module("telegram.handlers")
    return importlib.import_module("telegram.handlers.handover")


def test_handover_check_command(monkeypatch):
    _install_aiogram_stubs()
    handover = _reload_handover_module()

    get_mock = AsyncMock(
        side_effect=[
            {"projects": [{"id": "p-1"}]},
            {"completion_percent": 87, "missing": ["журнал бетонных работ"]},
        ]
    )
    monkeypatch.setattr(handover.api_client, "get", get_mock)

    callback = SimpleNamespace(
        data="handover_section:КЖ",
        from_user=SimpleNamespace(id=5),
        message=SimpleNamespace(answer=AsyncMock()),
        answer=AsyncMock(),
    )

    asyncio.run(handover.handover_section_callback_handler(callback))

    get_mock.assert_any_await("/api/projects")
    get_mock.assert_any_await("/api/compliance/gsn-checklist/p-1/section/кж")
    callback.message.answer.assert_awaited_once_with(
        "✅ КЖ: 87% готов. Отсутствует: журнал бетонных работ"
    )


def test_handover_forecast_command(monkeypatch):
    _install_aiogram_stubs()
    handover = _reload_handover_module()

    get_mock = AsyncMock(
        side_effect=[
            {"projects": [{"id": "p-42"}]},
            {
                "forecast_completion": "15 мая 2025",
                "average_delay_days": 4.5,
                "top_risk": "КМ-раздел — отставание 12 дней",
            },
        ]
    )
    monkeypatch.setattr(handover.api_client, "get", get_mock)

    message = SimpleNamespace(answer=AsyncMock())

    asyncio.run(handover.handover_forecast_handler(message))

    get_mock.assert_any_await("/api/projects")
    get_mock.assert_any_await("/api/analytics/schedule/p-42")
    message.answer.assert_awaited_once_with(
        "📅 Прогноз завершения: 15 мая 2025\n"
        "⚠️ Задержка: в среднем 4.5 дня\n"
        "🔴 Риски: КМ-раздел — отставание 12 дней"
    )
