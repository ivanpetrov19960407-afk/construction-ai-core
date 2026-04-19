"""Точка входа Telegram-бота на aiogram 3."""

import asyncio
import contextlib

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config.settings import settings
from telegram.handlers import router
from telegram.handlers.handover import router as handover_router
from telegram.middlewares.auth import TelegramAuthMiddleware
from telegram.middlewares.rate_limit import TelegramRateLimitMiddleware


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.message.middleware(TelegramRateLimitMiddleware())
    dp.callback_query.middleware(TelegramRateLimitMiddleware())
    dp.message.middleware(TelegramAuthMiddleware())
    dp.callback_query.middleware(TelegramAuthMiddleware())
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
    try:
        if not settings.telegram_webhook_url:
            await dp.start_polling(bot)
            return

        if settings.telegram_webhook_secret:
            await bot.set_webhook(
                settings.telegram_webhook_url,
                secret_token=settings.telegram_webhook_secret,
            )
        else:
            await bot.set_webhook(settings.telegram_webhook_url)
        await asyncio.Event().wait()
    finally:
        with contextlib.suppress(Exception):
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
