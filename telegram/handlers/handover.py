"""Хэндлеры для сценариев сдачи объекта."""

from __future__ import annotations

from collections.abc import Mapping

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from telegram.handlers import api_client

router = Router()

SECTION_TO_API = {
    "КЖ": "KZH",
    "КМ": "KM",
    "ОВ": "OV",
    "ВК": "VK",
    "ЭМ": "EM",
    "Все разделы": "ALL",
}


def _section_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"handover_section:{label}")]
        for label in SECTION_TO_API
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


def _missing_names(payload: Mapping) -> list[str]:
    raw_missing = payload.get("missing", [])
    if not isinstance(raw_missing, list):
        return []
    names: list[str] = []
    for item in raw_missing:
        if isinstance(item, Mapping):
            name = str(item.get("name", "")).strip()
            if name:
                names.append(name)
        elif isinstance(item, str) and item.strip():
            names.append(item.strip())
    return names


@router.message(Command("handover_check"))
async def handover_check_handler(message: Message) -> None:
    await message.answer("Выберите раздел для проверки", reply_markup=_section_keyboard())


@router.callback_query(F.data.startswith("handover_section:"))
async def handover_section_callback_handler(callback: CallbackQuery) -> None:
    section_label = (callback.data or "").split(":", maxsplit=1)[1]
    section_code = SECTION_TO_API.get(section_label)
    if section_code is None:
        await callback.answer("Неизвестный раздел")
        return

    project_id = await _get_default_project_id()
    if callback.message is None:
        await callback.answer()
        return
    if not project_id:
        await callback.message.answer("Проект не найден.")
        await callback.answer()
        return

    if section_code == "ALL":
        data = await api_client.get(f"/api/compliance/gsn-checklist/{project_id}")
        completion_pct = data.get("completion_pct", 0)
        sections = data.get("sections", [])
        all_missing: list[str] = []
        if isinstance(sections, list):
            for section in sections:
                if isinstance(section, Mapping):
                    all_missing.extend(_missing_names(section))
        missing_preview = ", ".join(all_missing[:3]) if all_missing else "нет"
        await callback.message.answer(
            f"✅ Все разделы: {completion_pct}% готов. Отсутствует: {missing_preview}"
        )
        await callback.answer()
        return

    data = await api_client.get(
        f"/api/compliance/gsn-checklist/{project_id}/section/{section_code}"
    )
    completion_pct = data.get("completion_pct", 0)
    missing_names = _missing_names(data)
    missing_str = ", ".join(missing_names[:3]) if missing_names else "нет"
    await callback.message.answer(
        f"✅ {section_label}: {completion_pct}% готов. Отсутствует: {missing_str}"
    )
    await callback.answer()


@router.message(Command("handover_forecast"))
async def handover_forecast_handler(message: Message) -> None:
    project_id = await _get_default_project_id()
    if not project_id:
        await message.answer("Проект не найден.")
        return

    data = await api_client.get(f"/api/analytics/schedule/{project_id}")
    finish = data.get("predicted_completion") or data.get("forecast_completion") or "—"
    avg_delay = data.get("avg_delay_days")
    if avg_delay is None:
        avg_delay = data.get("average_delay_days", 0)
    risks = data.get("risks", [])
    if isinstance(risks, list) and risks:
        first_risk = risks[0]
        if isinstance(first_risk, Mapping):
            section = first_risk.get("section", "раздел")
            description = first_risk.get("description", "")
            risk_text = f"{section} — {description}".strip(" —")
        else:
            risk_text = str(first_risk)
    else:
        risk_text = data.get("top_risk", "нет")

    await message.answer(
        "\n".join(
            [
                f"📅 Прогноз завершения: {finish}",
                f"⚠️ Задержка: в среднем {avg_delay} дня",
                f"🔴 Риски: {risk_text}",
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
        "doc_type": "aosr",
        "user_id": str(callback.from_user.id),
    }
    await api_client.post("/api/sign/document", payload)
    await callback.message.answer(f"Документ {doc_id} отправлен на подпись.")
    await callback.answer("Подписано")
