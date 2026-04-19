"""Приложенческие ошибки домена Core."""

from dataclasses import dataclass


@dataclass(slots=True)
class AppError(Exception):
    """Базовая доменная ошибка приложения."""

    message: str
    code: str = "app_error"
    status_code: int = 500

    def __str__(self) -> str:
        return self.message


class LLMProviderNotConfiguredError(AppError):
    """Ошибка конфигурации LLM-провайдера (ключ отсутствует)."""

    def __init__(self, provider: str, missing_setting: str):
        super().__init__(
            message=(
                f"LLM-провайдер '{provider}' не настроен: "
                f"заполните переменную {missing_setting.upper()}"
            ),
            code="llm_not_configured",
            status_code=503,
        )
        self.provider = provider
        self.missing_setting = missing_setting
