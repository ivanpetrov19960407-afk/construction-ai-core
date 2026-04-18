"""Точка входа Telegram-бота на aiogram 3."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config.settings import settings
from telegram.handlers import router
from telegram.handlers.handover import router as handover_router


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(router)
    dp.include_router(handover_router)
    return dp


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def main() -> None:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN не задан в настройках")

    bot = create_bot()
    dp = create_dispatcher()
    if not settings.telegram_webhook_url:
        await dp.start_polling(bot)
        return

    webhook_kwargs: dict[str, str] = {}
    if settings.telegram_webhook_secret:
        webhook_kwargs["secret_token"] = settings.telegram_webhook_secret
    await bot.set_webhook(settings.telegram_webhook_url, **webhook_kwargs)
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
