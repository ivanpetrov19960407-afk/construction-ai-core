"""Хэндлеры Telegram-бота."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from io import BytesIO

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyKeyboardRemove,
    WebAppInfo,
)

from config.settings import settings
from telegram.keyboards import (
    cancel_keyboard,
    confirm_keyboard,
    letter_type_keyboard,
    main_menu_keyboard,
    role_keyboard,
    skip_keyboard,
    unit_keyboard,
)
from telegram.states import AnalyzeForm, KSStates, LetterStates, TKStates, UploadForm

router = Router()

user_roles: dict[int, str] = {}


ROLE_NAMES = {
    "pto_engineer": "ПТО",
    "foreman": "Прораб",
    "tender_specialist": "Тендеры",
    "admin": "Админ",
}

_PERIOD_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}\s*-\s*\d{2}\.\d{2}\.\d{4}$")


def _get_api_key() -> str:
    """Возвращает первый API-ключ из настроек."""
    if settings.api_keys:
        return settings.api_keys[0]
    return ""


def _get_admin_api_key() -> str:
    """Возвращает первый admin API-ключ из настроек."""
    if settings.admin_api_keys:
        return settings.admin_api_keys[0]
    return _get_api_key()


@dataclass
class TelegramCoreClient:
    """Клиент для запросов к Construction AI Core API."""

    base_url: str

    async def post(self, path: str, payload: dict) -> dict:
        headers = {"X-API-Key": _get_api_key()}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()


api_client = TelegramCoreClient(base_url=settings.core_api_url.rstrip("/"))
MAX_PDF_SIZE_BYTES = 20_971_520


def _get_user_role(user_id: int) -> str:
    return user_roles.get(user_id, "pto_engineer")


def _require_user_id(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("Message has no from_user")
    return message.from_user.id


async def _call_api_with_typing(
    message: Message,
    path: str,
    payload: dict,
    timeout: float = 120.0,
) -> dict | None:
    """POST к API с typing-action и таймаутом."""
    bot = message.bot
    chat_id = message.chat.id

    async def _typing_loop() -> None:
        while True:
            if bot is not None:
                await bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(5)

    typing_task = asyncio.create_task(_typing_loop())
    try:
        headers = {"X-API-Key": _get_api_key()}
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                f"{settings.core_api_url.rstrip('/')}{path}",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
    except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
        await message.answer(f"Ошибка при обращении к API: {exc}")
        return None
    finally:
        typing_task.cancel()


# ── /start, /role ─────────────────────────────────────────────────────────────


@router.message(Command("start"))
async def start_handler(message: Message) -> None:
    await message.answer(
        "Привет! Я Construction AI Bot.",
        reply_markup=main_menu_keyboard(),
    )
    await message.answer(
        "Привет! Я Construction AI Bot. Выберите роль для работы:",
        reply_markup=role_keyboard(),
    )


@router.message(Command("role"))
async def role_handler(message: Message) -> None:
    await message.answer("Выберите новую роль:", reply_markup=role_keyboard())


@router.message(Command("app"))
async def app_handler(message: Message) -> None:
    webapp_url = f"https://{settings.domain}/web"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🌐 Открыть Web-приложение",
                    web_app=WebAppInfo(url=webapp_url),
                )
            ]
        ],
    )
    await message.answer("Откройте мини-приложение:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("role:"))
async def role_callback_handler(callback: CallbackQuery) -> None:
    data = callback.data or ""
    if ":" not in data:
        await callback.answer("Некорректный callback")
        return
    role = data.split(":", maxsplit=1)[1]
    user_roles[callback.from_user.id] = role
    if callback.message is not None:
        await callback.message.answer(f"Роль переключена: {ROLE_NAMES.get(role, role)}")
    await callback.answer("Роль сохранена")


# ── /tk — Технологическая карта (TKStates) ────────────────────────────────────


@router.message(Command("tk"))
async def tk_start_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(TKStates.work_type)
    await message.answer("Введите вид работ:", reply_markup=cancel_keyboard())


@router.message(TKStates.work_type)
async def tk_work_type_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(work_type=message.text)
    await state.set_state(TKStates.object_name)
    await message.answer("Введите наименование объекта:")


@router.message(TKStates.object_name)
async def tk_object_name_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(object_name=message.text)
    await state.set_state(TKStates.volume)
    await message.answer("Введите объём работ (число):")


@router.message(TKStates.volume)
async def tk_volume_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    try:
        float(text)
    except ValueError:
        await message.answer("Введите корректное число для объёма.")
        return
    await state.update_data(volume=text)
    await state.set_state(TKStates.unit)
    await message.answer("Выберите единицу измерения:", reply_markup=unit_keyboard())


@router.callback_query(F.data.startswith("unit:"))
async def tk_unit_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    unit = (callback.data or "").split(":", maxsplit=1)[1]
    await state.update_data(unit=unit)
    await state.set_state(TKStates.norms)
    if callback.message is not None:
        await callback.message.answer(
            "Введите ссылки на нормативы (или нажмите Пропустить):",
            reply_markup=skip_keyboard(),
        )
    await callback.answer()


@router.message(TKStates.unit)
async def tk_unit_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(unit=message.text)
    await state.set_state(TKStates.norms)
    await message.answer(
        "Введите ссылки на нормативы (или нажмите Пропустить):",
        reply_markup=skip_keyboard(),
    )


@router.message(TKStates.norms)
async def tk_norms_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    norms = "" if text.lower() == "пропустить" else text
    await state.update_data(norms=norms)
    await state.set_state(TKStates.confirm)
    data = await state.get_data()
    summary = (
        f"Вид работ: {data['work_type']}\n"
        f"Объект: {data['object_name']}\n"
        f"Объём: {data['volume']} {data['unit']}\n"
        f"Нормативы: {norms or '—'}\n\n"
        "Генерировать ТК?"
    )
    await message.answer(summary, reply_markup=confirm_keyboard())


@router.callback_query(F.data == "confirm:yes", TKStates.confirm)
async def tk_confirm_yes_handler(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    if callback.message is None or not isinstance(callback.message, Message):
        return
    message = callback.message
    user_id = callback.from_user.id
    payload = {
        "work_type": data["work_type"],
        "object_name": data["object_name"],
        "volume": float(data["volume"]),
        "unit": data["unit"],
        "norms": data.get("norms", ""),
        "session_id": str(user_id),
        "role": _get_user_role(user_id),
    }
    response = await _call_api_with_typing(message, "/api/generate/tk", payload)
    if response is not None:
        await _send_generated_document(message, response, "tk")
    await callback.answer()


# ── /letter — Деловое письмо (LetterStates) ───────────────────────────────────


@router.message(Command("letter"))
async def letter_start_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(LetterStates.letter_type)
    await message.answer(
        "Выберите тип письма:",
        reply_markup=letter_type_keyboard(),
    )


@router.callback_query(F.data.startswith("letter_type:"))
async def letter_type_callback_handler(callback: CallbackQuery, state: FSMContext) -> None:
    lt = (callback.data or "").split(":", maxsplit=1)[1]
    await state.update_data(letter_type=lt)
    await state.set_state(LetterStates.addressee)
    if callback.message is not None:
        await callback.message.answer("Введите адресата:", reply_markup=cancel_keyboard())
    await callback.answer()


@router.message(LetterStates.letter_type)
async def letter_type_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(letter_type=message.text)
    await state.set_state(LetterStates.addressee)
    await message.answer("Введите адресата:", reply_markup=cancel_keyboard())


@router.message(LetterStates.addressee)
async def letter_addressee_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(addressee=message.text)
    await state.set_state(LetterStates.subject)
    await message.answer("Введите тему письма:")


@router.message(LetterStates.subject)
async def letter_subject_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(subject=message.text)
    await state.set_state(LetterStates.body_points)
    await state.update_data(body_points=[])
    await message.answer("Введите тезисы по одному. Когда закончите, отправьте «готово».")


@router.message(LetterStates.body_points)
async def letter_body_points_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.lower() == "готово":
        data = await state.get_data()
        points = data.get("body_points", [])
        if not points:
            await message.answer("Нужно ввести хотя бы один тезис.")
            return
        await state.set_state(LetterStates.contract_number)
        await message.answer(
            "Введите номер договора (или нажмите Пропустить):",
            reply_markup=skip_keyboard(),
        )
        return
    if not text:
        await message.answer("Тезис не может быть пустым.")
        return
    data = await state.get_data()
    points = data.get("body_points", [])
    points.append(text)
    await state.update_data(body_points=points)
    await message.answer(f"Тезис #{len(points)} добавлен. Следующий или «готово».")


@router.message(LetterStates.contract_number)
async def letter_contract_number_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    contract = "" if text.lower() == "пропустить" else text
    await state.update_data(contract_number=contract)
    await state.set_state(LetterStates.confirm)
    data = await state.get_data()
    points_str = "\n".join(f"  • {p}" for p in data["body_points"])
    summary = (
        f"Тип: {data['letter_type']}\n"
        f"Адресат: {data['addressee']}\n"
        f"Тема: {data['subject']}\n"
        f"Тезисы:\n{points_str}\n"
        f"Договор: {contract or '—'}\n\n"
        "Генерировать письмо?"
    )
    await message.answer(summary, reply_markup=confirm_keyboard())


@router.callback_query(F.data == "confirm:yes", LetterStates.confirm)
async def letter_confirm_yes_handler(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    if callback.message is None or not isinstance(callback.message, Message):
        return
    message = callback.message
    user_id = callback.from_user.id
    payload = {
        "letter_type": data["letter_type"],
        "addressee": data["addressee"],
        "subject": data["subject"],
        "body_points": data["body_points"],
        "contract_number": data.get("contract_number", ""),
        "session_id": str(user_id),
        "role": _get_user_role(user_id),
    }
    response = await _call_api_with_typing(message, "/api/generate/letter", payload)
    if response is not None:
        await _send_generated_document(message, response, "letter")
    await callback.answer()


# ── /ks — Акт КС-2/КС-3 (KSStates) ──────────────────────────────────────────


@router.message(Command("ks"))
async def ks_start_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(KSStates.object_name)
    await message.answer("Введите наименование объекта:", reply_markup=cancel_keyboard())


@router.message(KSStates.object_name)
async def ks_object_name_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(object_name=message.text)
    await state.set_state(KSStates.contract_number)
    await message.answer("Введите номер договора:")


@router.message(KSStates.contract_number)
async def ks_contract_number_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(contract_number=message.text)
    await state.set_state(KSStates.period)
    await message.answer("Введите период (ДД.ММ.ГГГГ - ДД.ММ.ГГГГ):")


@router.message(KSStates.period)
async def ks_period_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not _PERIOD_RE.match(text):
        await message.answer("Неверный формат. Введите период в формате ДД.ММ.ГГГГ - ДД.ММ.ГГГГ")
        return
    await state.update_data(period=text)
    await state.set_state(KSStates.work_items)
    await state.update_data(work_items=[])
    await message.answer("Введите позиции работ по одной. Когда закончите, отправьте «готово».")


@router.message(KSStates.work_items)
async def ks_work_items_handler(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.lower() == "готово":
        data = await state.get_data()
        items = data.get("work_items", [])
        if not items:
            await message.answer("Нужно ввести хотя бы одну позицию работ.")
            return
        await state.set_state(KSStates.confirm)
        items_str = "\n".join(f"  • {it}" for it in items)
        summary = (
            f"Объект: {data['object_name']}\n"
            f"Договор: {data['contract_number']}\n"
            f"Период: {data['period']}\n"
            f"Работы:\n{items_str}\n\n"
            "Генерировать акт КС?"
        )
        await message.answer(summary, reply_markup=confirm_keyboard())
        return
    if not text:
        await message.answer("Позиция работ не может быть пустой.")
        return
    data = await state.get_data()
    items = data.get("work_items", [])
    items.append(text)
    await state.update_data(work_items=items)
    await message.answer(f"Позиция #{len(items)} добавлена. Следующая или «готово».")


@router.callback_query(F.data == "confirm:yes", KSStates.confirm)
async def ks_confirm_yes_handler(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    if callback.message is None or not isinstance(callback.message, Message):
        return
    message = callback.message
    user_id = callback.from_user.id
    payload = {
        "object_name": data["object_name"],
        "contract_number": data["contract_number"],
        "period": data["period"],
        "work_items": data["work_items"],
        "session_id": str(user_id),
        "role": _get_user_role(user_id),
    }
    response = await _call_api_with_typing(message, "/api/generate/ks", payload)
    if response is not None:
        await _send_generated_document(message, response, "ks")
    await callback.answer()


# ── confirm:no — общий для всех форм ─────────────────────────────────────────


@router.callback_query(F.data == "confirm:no")
async def confirm_no_handler(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    if callback.message is not None:
        await callback.message.answer("Генерация отменена.", reply_markup=ReplyKeyboardRemove())
    await callback.answer("Отменено")


# ── Анализ тендера ────────────────────────────────────────────────────────────


@router.message(Command("analyze"))
@router.message(F.text == "📋 Анализ тендера")
async def analyze_start_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(AnalyzeForm.document)
    await message.answer("Отправь PDF-документ для анализа", reply_markup=cancel_keyboard())


@router.message(AnalyzeForm.document, F.document)
async def analyze_document_handler(message: Message, state: FSMContext) -> None:
    document = message.document
    if document is None:
        await message.answer("Отправь документ в формате PDF.")
        return

    if document.file_size and document.file_size > MAX_PDF_SIZE_BYTES:
        await message.answer("Файл слишком большой (макс. 20 МБ)")
        return

    file_name = document.file_name or ""
    if document.mime_type != "application/pdf" and not file_name.lower().endswith(".pdf"):
        await message.answer("Поддерживаются только PDF-документы.")
        return

    file_bytes = BytesIO()
    bot = message.bot
    if bot is None:
        await message.answer("Bot не инициализирован.")
        return
    await bot.download(document, destination=file_bytes)
    file_bytes.seek(0)

    result = await _analyze_tender_pdf(file_name or "tender.pdf", file_bytes.getvalue())
    await state.clear()
    await message.answer(_format_analyze_response(result), reply_markup=ReplyKeyboardRemove())


# ── Загрузка нормативов в RAG ────────────────────────────────────────────────


@router.message(Command("upload"))
async def upload_start_handler(message: Message, state: FSMContext) -> None:
    user_id = _require_user_id(message)
    if user_id not in settings.admin_telegram_ids:
        await message.answer("⛔ Команда доступна только администраторам.")
        return
    await state.set_state(UploadForm.document)
    await message.answer("Отправь PDF для загрузки в базу знаний", reply_markup=cancel_keyboard())


@router.message(UploadForm.document, F.document)
async def upload_document_handler(message: Message, state: FSMContext) -> None:
    user_id = _require_user_id(message)
    if user_id not in settings.admin_telegram_ids:
        await state.clear()
        await message.answer("⛔ Команда доступна только администраторам.")
        return

    document = message.document
    if document is None:
        await message.answer("Отправь документ в формате PDF.")
        return

    if document.file_size and document.file_size > MAX_PDF_SIZE_BYTES:
        await message.answer("Файл слишком большой (макс. 20 МБ)")
        return

    file_name = document.file_name or "document.pdf"
    if document.mime_type != "application/pdf" and not file_name.lower().endswith(".pdf"):
        await message.answer("Поддерживаются только PDF-документы.")
        return

    bot = message.bot
    if bot is None:
        await message.answer("Bot не инициализирован.")
        return

    file_bytes = BytesIO()
    await bot.download(document, destination=file_bytes)
    file_bytes.seek(0)

    try:
        result = await _ingest_rag_pdf(file_name, file_bytes.getvalue())
    except (httpx.TimeoutException, httpx.HTTPStatusError) as exc:
        await message.answer(f"Ошибка загрузки в базу знаний: {exc}")
        return

    chunks_added = int(result.get("chunks_added", 0))
    source = str(result.get("source", file_name))
    await state.clear()
    await message.answer(
        f"✅ Загружено {chunks_added} chunks из документа {source}",
        reply_markup=ReplyKeyboardRemove(),
    )


# ── Отмена и текстовый fallback ───────────────────────────────────────────────


@router.message(F.text.casefold() == "отмена")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())


@router.message()
async def text_message_handler(message: Message) -> None:
    user_id = _require_user_id(message)
    payload = {
        "message": message.text,
        "session_id": str(user_id),
        "role": _get_user_role(user_id),
    }
    response = await api_client.post("/api/chat", payload)
    await message.answer(response.get("reply", "Нет ответа от API"))


# ── Утилиты ──────────────────────────────────────────────────────────────────


async def _send_generated_document(message: Message, response: Mapping, doc_prefix: str) -> None:
    document = response.get("document")
    if isinstance(document, Mapping):
        text_payload = json.dumps(document, ensure_ascii=False, indent=2)
    else:
        text_payload = str(document)

    user_id = message.chat.id
    file_data = text_payload.encode("utf-8")
    input_file = BufferedInputFile(file_data, filename=f"{doc_prefix}_{user_id}.txt")
    await message.answer_document(input_file, caption="Документ сформирован.")
    await message.answer("Готово ✅", reply_markup=ReplyKeyboardRemove())


async def _analyze_tender_pdf(filename: str, content: bytes) -> dict:
    headers = {"X-API-Key": _get_api_key()}
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.core_api_url.rstrip('/')}/api/analyze/tender",
            files={"file": (filename, content, "application/pdf")},
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


async def _ingest_rag_pdf(filename: str, content: bytes) -> dict:
    headers = {"X-API-Key": _get_admin_api_key()}
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{settings.core_api_url.rstrip('/')}/api/rag/ingest",
            files={
                "file": (filename, content, "application/pdf"),
                "source_name": (None, filename),
            },
            headers=headers,
        )
        response.raise_for_status()
        return response.json()


def _format_analyze_response(data: Mapping) -> str:
    risks = data.get("risks", []) if isinstance(data.get("risks"), list) else []
    contradictions = data.get("contradictions", {})
    mismatches: list = []
    if isinstance(contradictions, Mapping):
        mismatches = contradictions.get("mismatches", [])
        if not isinstance(mismatches, list):
            mismatches = contradictions.get("non_compliances", [])
    mismatches = mismatches if isinstance(mismatches, list) else []
    legal_issues_raw = data.get("legal_issues", [])
    legal_issues = legal_issues_raw if isinstance(legal_issues_raw, list) else []
    recommendation = data.get("recommendation", "УТОЧНИТЬ")
    confidence = data.get("confidence", 0)
    is_fraction = isinstance(confidence, (int, float)) and confidence <= 1
    confidence_pct = int(float(confidence) * 100) if is_fraction else int(confidence)

    risks_block = "\n".join([f"• {item}" for item in risks]) or "• Нет"
    mismatches_block = "\n".join([f"• {item}" for item in mismatches]) or "• Нет"
    legal_issues_block = "\n".join([f"• {item}" for item in legal_issues]) or "• Нет"

    return (
        f"🔴 Риски ({len(risks)}):\n"
        f"{risks_block}\n\n"
        f"🟡 Несоответствия ({len(mismatches)}):\n"
        f"{mismatches_block}\n\n"
        f"⚖️ Юр. замечания ({len(legal_issues)}):\n"
        f"{legal_issues_block}\n\n"
        f"✅ Рекомендация: {recommendation}\n"
        f"Уверенность: {confidence_pct}%"
    )
