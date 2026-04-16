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
        keyboard=[
            [
                KeyboardButton(text="📋 АОСР"),
                KeyboardButton(text="📊 КГ"),
                KeyboardButton(text="✅ Сдача объекта"),
                KeyboardButton(text="❓ Помощь"),
            ]
        ],
        resize_keyboard=True,
    )


def unit_keyboard() -> InlineKeyboardMarkup:
    """Inline-клавиатура выбора единицы измерения."""
    units = ["м³", "м²", "пог.м.", "шт.", "т", "кг"]
    buttons = [[InlineKeyboardButton(text=u, callback_data=f"unit:{u}")] for u in units]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def letter_type_keyboard() -> InlineKeyboardMarkup:
    """Inline-клавиатура выбора типа письма."""
    types = ["Запрос", "Претензия", "Уведомление", "Ответ"]
    buttons = [[InlineKeyboardButton(text=t, callback_data=f"letter_type:{t}")] for t in types]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_keyboard() -> InlineKeyboardMarkup:
    """Inline-клавиатура подтверждения генерации."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Генерировать", callback_data="confirm:yes"),
                InlineKeyboardButton(text="❌ Отмена", callback_data="confirm:no"),
            ]
        ]
    )


def skip_keyboard() -> ReplyKeyboardMarkup:
    """Reply-клавиатура с кнопками Пропустить и Отмена."""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Пропустить"), KeyboardButton(text="Отмена")],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
