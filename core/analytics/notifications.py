"""Scheduler for daily delay notifications to PTO engineer in Telegram."""

from __future__ import annotations

import asyncio
import datetime as dt
from typing import Any

import aiosqlite
import structlog
from aiogram import Bot

from config.settings import settings
from core.analytics.schedule_predictor import SchedulePredictor

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.triggers.cron import CronTrigger
except Exception:  # noqa: BLE001
    AsyncIOScheduler = None
    CronTrigger = None


class AnalyticsNotifier:
    """Run daily analytics checks and notify responsible engineers."""

    def __init__(self) -> None:
        self._logger = structlog.get_logger("core.analytics.notifications")
        self._predictor = SchedulePredictor()
        self._scheduler: Any | None = None
        self._utc = getattr(dt, "UTC", dt.timezone.utc)  # noqa: UP017

    async def start(self) -> None:
        """Start APScheduler job if dependency is available."""
        if AsyncIOScheduler is None or CronTrigger is None:
            self._logger.warning("apscheduler_unavailable")
            return

        scheduler = AsyncIOScheduler(timezone="Europe/Moscow")
        scheduler.add_job(
            self.check_and_notify_projects,
            trigger=CronTrigger(hour=9, minute=0),
            id="analytics_daily_delay_check",
            replace_existing=True,
        )
        scheduler.start()
        self._scheduler = scheduler

    async def stop(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)

    async def check_and_notify_projects(self) -> None:
        """Check projects with high delay_rate and send Telegram notifications."""
        project_ids = await self._get_all_project_ids()
        if not project_ids or not settings.bot_token or not settings.admin_telegram_ids:
            return

        bot = Bot(token=settings.bot_token)
        now = dt.datetime.now(self._utc).strftime("%Y-%m-%d %H:%M UTC")
        try:
            for project_id in project_ids:
                quick_prediction = await self._predictor.predict_completion(
                    project_id,
                    include_llm=False,
                )
                if float(quick_prediction.get("delay_rate", 0.0)) <= 0.3:
                    continue
                prediction = await self._predictor.predict_completion(project_id, include_llm=True)

                message = (
                    "⚠️ Риск срыва сроков\n"
                    f"Проект: {project_id}\n"
                    f"Delay rate: {prediction['delay_rate']:.0%}\n"
                    f"Прогноз завершения: {prediction.get('predicted_completion')}\n"
                    f"Проверка: {now}"
                )
                for chat_id in settings.admin_telegram_ids:
                    await bot.send_message(chat_id=chat_id, text=message)
        finally:
            await bot.session.close()

    async def _get_all_project_ids(self) -> list[str]:
        query = "SELECT id FROM projects"
        try:
            async with aiosqlite.connect(settings.sqlite_db_path) as db:
                rows = await db.execute_fetchall(query)
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("projects_list_failed", error=str(exc))
            return []

        return [str(row[0]) for row in rows]


async def run_daily_delay_check() -> None:
    """Standalone entrypoint for external schedulers/celery beat."""
    await AnalyticsNotifier().check_and_notify_projects()


def run_daily_delay_check_sync() -> None:
    """Sync wrapper for task queues that require sync callables."""
    asyncio.run(run_daily_delay_check())
