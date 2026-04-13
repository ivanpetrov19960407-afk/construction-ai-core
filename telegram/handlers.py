"""Хэндлеры Telegram-бота."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message, ReplyKeyboardRemove

from config.settings import settings
from telegram.keyboards import cancel_keyboard, role_keyboard

router = Router()

user_roles: dict[int, str] = {}


ROLE_NAMES = {
    "pto_engineer": "ПТО",
    "foreman": "Прораб",
    "tender_specialist": "Тендеры",
    "admin": "Админ",
}


@dataclass
class TelegramCoreClient:
    """Клиент для запросов к Construction AI Core API."""

    base_url: str

    async def post(self, path: str, payload: dict) -> dict:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(f"{self.base_url}{path}", json=payload)
            response.raise_for_status()
            return response.json()


api_client = TelegramCoreClient(base_url=settings.core_api_url.rstrip("/"))


class TKForm(StatesGroup):
    work_type = State()
    object_name = State()
    volume = State()
    unit = State()


class LetterForm(StatesGroup):
    letter_type = State()
    addressee = State()
    subject = State()
    body_points = State()


def _get_user_role(user_id: int) -> str:
    return user_roles.get(user_id, "pto_engineer")


@router.message(Command("start"))
async def start_handler(message: Message) -> None:
    await message.answer(
        "Привет! Я Construction AI Bot. Выберите роль для работы:",
        reply_markup=role_keyboard(),
    )


@router.message(Command("role"))
async def role_handler(message: Message) -> None:
    await message.answer("Выберите новую роль:", reply_markup=role_keyboard())


@router.callback_query(F.data.startswith("role:"))
async def role_callback_handler(callback: CallbackQuery) -> None:
    role = callback.data.split(":", maxsplit=1)[1]
    user_roles[callback.from_user.id] = role
    await callback.message.answer(f"Роль переключена: {ROLE_NAMES.get(role, role)}")
    await callback.answer("Роль сохранена")


@router.message(Command("tk"))
async def tk_start_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(TKForm.work_type)
    await message.answer("Введите вид работ:", reply_markup=cancel_keyboard())


@router.message(TKForm.work_type)
async def tk_work_type_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(work_type=message.text)
    await state.set_state(TKForm.object_name)
    await message.answer("Введите наименование объекта:")


@router.message(TKForm.object_name)
async def tk_object_name_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(object_name=message.text)
    await state.set_state(TKForm.volume)
    await message.answer("Введите объём работ (число):")


@router.message(TKForm.volume)
async def tk_volume_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(volume=message.text)
    await state.set_state(TKForm.unit)
    await message.answer("Введите единицу измерения (например: м², м³, шт.):")


@router.message(TKForm.unit)
async def tk_unit_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(unit=message.text)
    data = await state.get_data()
    await state.clear()

    payload = {
        "work_type": data["work_type"],
        "object_name": data["object_name"],
        "volume": float(data["volume"]),
        "unit": data["unit"],
        "session_id": str(message.from_user.id),
        "role": _get_user_role(message.from_user.id),
    }
    response = await api_client.post("/api/generate/tk", payload)
    await _send_generated_document(message, response, "tk")


@router.message(Command("letter"))
async def letter_start_handler(message: Message, state: FSMContext) -> None:
    await state.set_state(LetterForm.letter_type)
    await message.answer(
        "Введите тип письма (запрос, претензия, уведомление, ответ):",
        reply_markup=cancel_keyboard(),
    )


@router.message(LetterForm.letter_type)
async def letter_type_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(letter_type=message.text)
    await state.set_state(LetterForm.addressee)
    await message.answer("Введите адресата:")


@router.message(LetterForm.addressee)
async def letter_addressee_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(addressee=message.text)
    await state.set_state(LetterForm.subject)
    await message.answer("Введите тему письма:")


@router.message(LetterForm.subject)
async def letter_subject_handler(message: Message, state: FSMContext) -> None:
    await state.update_data(subject=message.text)
    await state.set_state(LetterForm.body_points)
    await message.answer("Введите тезисы письма (через ';'):")


@router.message(LetterForm.body_points)
async def letter_body_points_handler(message: Message, state: FSMContext) -> None:
    body_points = [p.strip() for p in (message.text or "").split(";") if p.strip()]
    await state.update_data(body_points=body_points)
    data = await state.get_data()
    await state.clear()

    payload = {
        "letter_type": data["letter_type"],
        "addressee": data["addressee"],
        "subject": data["subject"],
        "body_points": data["body_points"],
        "session_id": str(message.from_user.id),
        "role": _get_user_role(message.from_user.id),
    }
    response = await api_client.post("/api/generate/letter", payload)
    await _send_generated_document(message, response, "letter")


@router.message(F.text.casefold() == "отмена")
async def cancel_handler(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.", reply_markup=ReplyKeyboardRemove())


@router.message()
async def text_message_handler(message: Message) -> None:
    payload = {
        "message": message.text,
        "session_id": str(message.from_user.id),
        "role": _get_user_role(message.from_user.id),
    }
    response = await api_client.post("/api/chat", payload)
    await message.answer(response.get("reply", "Нет ответа от API"))


async def _send_generated_document(message: Message, response: Mapping, doc_prefix: str) -> None:
    document = response.get("document")
    if isinstance(document, Mapping):
        text_payload = json.dumps(document, ensure_ascii=False, indent=2)
    else:
        text_payload = str(document)

    file_data = text_payload.encode("utf-8")
    input_file = BufferedInputFile(file_data, filename=f"{doc_prefix}_{message.from_user.id}.txt")
    await message.answer_document(input_file, caption="Документ сформирован.")
    await message.answer("Готово ✅", reply_markup=ReplyKeyboardRemove())
