"""Хэндлеры для сценариев сдачи объекта."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from telegram.handlers import _get_user_role, api_client

router = Router()

SECTIONS = ["КЖ", "КМ", "ОВ", "ВК", "ЭМ", "Все разделы"]


def _section_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=section, callback_data=f"handover_section:{section}")]
        for section in SECTIONS
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _sign_confirm_keyboard(doc_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Да", callback_data=f"sign_doc:yes:{doc_id}"),
                InlineKeyboardButton(text="Нет", callback_data=f"sign_doc:no:{doc_id}"),
            ]
        ]
    )


async def _get_default_project_id() -> str | None:
    data = await api_client.get("/api/projects")
    projects = data.get("projects", [])
    if not projects:
        return None
    return projects[0].get("id")


@router.message(Command("handover_check"))
async def handover_check_handler(message: Message) -> None:
    await message.answer("Выберите раздел для проверки", reply_markup=_section_keyboard())


@router.callback_query(F.data.startswith("handover_section:"))
async def handover_section_callback_handler(callback: CallbackQuery) -> None:
    section = (callback.data or "").split(":", maxsplit=1)[1]
    project_id = await _get_default_project_id()
    if callback.message is None:
        await callback.answer()
        return
    if not project_id:
        await callback.message.answer("Проект не найден.")
        await callback.answer()
        return

    section_param = "all" if section == "Все разделы" else section.lower()
    data = await api_client.get(f"/api/compliance/gsn-checklist/{project_id}/section/{section_param}")

    percent = data.get("completion_percent", 0)
    missing = data.get("missing", [])
    missing_str = ", ".join(missing) if missing else "нет"
    await callback.message.answer(f"✅ {section}: {percent}% готов. Отсутствует: {missing_str}")
    await callback.answer()


@router.message(Command("handover_forecast"))
async def handover_forecast_handler(message: Message) -> None:
    project_id = await _get_default_project_id()
    if not project_id:
        await message.answer("Проект не найден.")
        return

    data = await api_client.get(f"/api/analytics/schedule/{project_id}")
    finish = data.get("forecast_completion", "—")
    avg_delay = data.get("average_delay_days", 0)
    risk = data.get("top_risk", "нет")
    await message.answer(
        "\n".join(
            [
                f"📅 Прогноз завершения: {finish}",
                f"⚠️ Задержка: в среднем {avg_delay} дня",
                f"🔴 Риски: {risk}",
            ]
        )
    )


@router.message(Command("sign_doc"))
async def sign_doc_handler(message: Message) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Использование: /sign_doc {doc_id}")
        return
    doc_id = parts[1].strip()
    await message.answer(
        f"Подписать АОСР №{doc_id} ЭЦП?",
        reply_markup=_sign_confirm_keyboard(doc_id),
    )


@router.callback_query(F.data.startswith("sign_doc:"))
async def sign_doc_callback_handler(callback: CallbackQuery) -> None:
    data = (callback.data or "").split(":")
    if len(data) != 3:
        await callback.answer("Некорректная команда")
        return
    action, doc_id = data[1], data[2]
    if callback.message is None:
        await callback.answer()
        return

    if action == "no":
        await callback.message.answer("Подписание отменено.")
        await callback.answer()
        return

    payload = {
        "doc_id": doc_id,
        "session_id": str(callback.from_user.id),
        "role": _get_user_role(callback.from_user.id),
    }
    await api_client.post("/api/sign/document", payload)
    await callback.message.answer(f"Документ {doc_id} отправлен на подпись.")
    await callback.answer("Подписано")
