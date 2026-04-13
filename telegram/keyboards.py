"""Клавиатуры для Telegram-бота."""

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

ROLE_BUTTONS = [
    ("ПТО", "pto_engineer"),
    ("Прораб", "foreman"),
    ("Тендеры", "tender_specialist"),
    ("Админ", "admin"),
]


def role_keyboard() -> InlineKeyboardMarkup:
    """Inline-клавиатура выбора роли."""
    buttons = [
        [InlineKeyboardButton(text=title, callback_data=f"role:{role}")]
        for title, role in ROLE_BUTTONS
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура с отменой текущего сценария."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Отмена")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Главное меню бота."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📋 Анализ тендера")]],
        resize_keyboard=True,
    )
