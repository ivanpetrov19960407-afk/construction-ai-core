"""FSM-состояния для Telegram-бота."""

from aiogram.fsm.state import State, StatesGroup


class TKStates(StatesGroup):
    """Шаги генерации технологической карты."""

    work_type = State()
    object_name = State()
    volume = State()
    unit = State()
    norms = State()
    confirm = State()


class LetterStates(StatesGroup):
    """Шаги генерации делового письма."""

    letter_type = State()
    addressee = State()
    subject = State()
    body_points = State()
    contract_number = State()
    confirm = State()


class KSStates(StatesGroup):
    """Шаги генерации акта КС-2/КС-3."""

    object_name = State()
    contract_number = State()
    period = State()
    work_items = State()
    confirm = State()


class AnalyzeForm(StatesGroup):
    """Состояние загрузки документа для анализа."""

    document = State()


class UploadForm(StatesGroup):
    """Состояние загрузки документа в базу знаний."""

    document = State()
