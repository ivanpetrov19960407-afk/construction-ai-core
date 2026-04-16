"""Analytics module for schedule delay prediction based on KG history."""

from __future__ import annotations

import datetime as dt
import json
from typing import TypedDict

import aiosqlite
import structlog

from config.settings import settings
from core.llm_router import LLMProvider, LLMRouter


class SchedulePredictor:
    """Predict project completion date from KG plan/fact history."""

    def __init__(self) -> None:
        self._logger = structlog.get_logger("core.analytics.schedule_predictor")
        self._llm_router = LLMRouter()
        self._utc = getattr(dt, "UTC", dt.timezone.utc)  # noqa: UP017

    async def get_project_history(self, project_id: str) -> list[dict]:
        """Получить историю план/факт из таблицы kg_entries за 90 дней."""
        cutoff = (dt.datetime.now(self._utc) - dt.timedelta(days=90)).date().isoformat()
        query = """
            SELECT
                id,
                project_id,
                COALESCE(section, '') AS section,
                COALESCE(task_name, title, 'task') AS task_name,
                planned_finish,
                planned_date,
                actual_finish,
                actual_date,
                status,
                is_closed,
                created_at,
                updated_at
            FROM kg_entries
            WHERE project_id = ?
              AND DATE(COALESCE(actual_finish, actual_date, updated_at, created_at)) >= DATE(?)
            ORDER BY COALESCE(actual_finish, actual_date, updated_at, created_at) DESC
        """

        try:
            async with aiosqlite.connect(settings.sqlite_db_path) as db:
                db.row_factory = aiosqlite.Row
                rows = await db.execute_fetchall(query, (project_id, cutoff))
        except Exception as exc:  # noqa: BLE001
            self._logger.warning(
                "kg_history_unavailable",
                project_id=project_id,
                error=str(exc),
            )
            return []

        return [dict(row) for row in rows]

    async def calculate_delay_stats(self, history: list) -> dict:
        """Рассчитать статистику задержек по завершённым задачам."""
        class CriticalSection(TypedDict):
            section: str
            avg_delay_days: float
            delayed_tasks: int

        completed = [row for row in history if self._is_closed(row)]
        if not completed:
            return {
                "avg_delay_days": 0.0,
                "delay_rate": 0.0,
                "critical_sections": [],
                "completed_tasks": 0,
            }

        delays_by_section: dict[str, list[int]] = {}
        delayed_count = 0
        delay_days_list: list[int] = []

        for task in completed:
            delay_days = self._delay_days(task)
            delay_days_list.append(delay_days)
            section = str(task.get("section") or "unknown")
            delays_by_section.setdefault(section, []).append(delay_days)
            if delay_days > 0:
                delayed_count += 1

        avg_delay = sum(delay_days_list) / len(delay_days_list)
        delay_rate = delayed_count / len(completed)

        critical_sections_unsorted: list[CriticalSection] = [
            {
                "section": section,
                "avg_delay_days": round(sum(values) / len(values), 2),
                "delayed_tasks": sum(1 for value in values if value > 0),
            }
            for section, values in delays_by_section.items()
        ]
        critical_sections = sorted(
            critical_sections_unsorted,
            key=lambda item: item["avg_delay_days"],
            reverse=True,
        )[:3]

        return {
            "avg_delay_days": round(avg_delay, 2),
            "delay_rate": round(delay_rate, 4),
            "critical_sections": critical_sections,
            "completed_tasks": len(completed),
        }

    async def predict_completion(self, project_id: str) -> dict:
        """Сформировать прогноз завершения проекта и рисков."""
        history = await self.get_project_history(project_id)
        stats = await self.calculate_delay_stats(history)
        open_tasks = await self._get_open_tasks(project_id)
        project_name = await self._get_project_name(project_id)

        adjusted_tasks = []
        avg_delay_days = float(stats["avg_delay_days"])
        for task in open_tasks:
            planned_finish = self._parse_date(
                task.get("planned_finish") or task.get("planned_date"),
            )
            predicted_finish = None
            if planned_finish is not None:
                predicted_finish = planned_finish + dt.timedelta(days=round(avg_delay_days))
            adjusted_tasks.append(
                {
                    **task,
                    "predicted_finish": predicted_finish.isoformat() if predicted_finish else None,
                }
            )

        predicted_dates: list[dt.date] = []
        for task in adjusted_tasks:
            parsed = self._parse_date(task.get("predicted_finish"))
            if parsed is not None:
                predicted_dates.append(parsed)
        latest_task_date = max(predicted_dates, default=None)
        predicted_completion = latest_task_date or dt.date.today()

        llm_result = await self._llm_assessment(project_name, stats, adjusted_tasks)
        return {
            "avg_delay_days": float(stats["avg_delay_days"]),
            "delay_rate": float(stats["delay_rate"]),
            "predicted_completion": predicted_completion.isoformat(),
            "risks": llm_result.get("risks", []),
            "recommendations": llm_result.get("recommendations", []),
            "critical_sections": stats["critical_sections"],
        }

    async def get_section_summary(self, project_id: str) -> list[dict]:
        """Return summary by KG sections for dashboard endpoint."""
        query = """
            SELECT
                COALESCE(section, 'unknown') AS section,
                COUNT(*) AS total_tasks,
                SUM(
                    CASE
                        WHEN COALESCE(is_closed, 0) = 1 OR status IN ('done', 'closed')
                        THEN 1
                        ELSE 0
                    END
                ) AS closed_tasks,
                SUM(
                    CASE
                        WHEN (COALESCE(is_closed, 0) = 1 OR status IN ('done', 'closed'))
                            AND DATE(COALESCE(actual_finish, actual_date)) > DATE(
                                COALESCE(planned_finish, planned_date)
                            )
                        THEN 1
                        ELSE 0
                    END
                ) AS delayed_tasks
            FROM kg_entries
            WHERE project_id = ?
            GROUP BY COALESCE(section, 'unknown')
            ORDER BY section
        """
        try:
            async with aiosqlite.connect(settings.sqlite_db_path) as db:
                db.row_factory = aiosqlite.Row
                rows = await db.execute_fetchall(query, (project_id,))
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("kg_sections_unavailable", project_id=project_id, error=str(exc))
            return []

        return [dict(row) for row in rows]

    async def _llm_assessment(
        self,
        project_name: str,
        stats: dict,
        tasks: list[dict],
    ) -> dict:
        prompt = (
            f"Проект {project_name}. Статистика: {json.dumps(stats, ensure_ascii=False)}. "
            f"Открытые задачи: {json.dumps(tasks, ensure_ascii=False)}. "
            "Дай прогноз завершения, топ-3 риска, рекомендации. Ответ JSON."
        )
        fallback = {
            "risks": [
                {
                    "section": "general",
                    "description": "Недостаточно данных для точной оценки рисков",
                    "severity": "medium",
                }
            ],
            "recommendations": [
                "Актуализировать план-факт данные КГ минимум раз в неделю",
                "Проверить критические разделы и перераспределить ресурсы",
            ],
        }
        try:
            response = await self._llm_router.query(
                prompt,
                provider=LLMProvider.OPENAI,
                model="gpt-4o-mini",
                temperature=0.2,
                max_tokens=1200,
            )
            parsed = self._parse_json_object(response.text)
            if parsed is None:
                return fallback
            return {
                "risks": parsed.get("risks", fallback["risks"]),
                "recommendations": parsed.get("recommendations", fallback["recommendations"]),
            }
        except Exception as exc:  # noqa: BLE001
            self._logger.warning("llm_schedule_prediction_failed", error=str(exc))
            return fallback

    async def _get_open_tasks(self, project_id: str) -> list[dict]:
        query = """
            SELECT
                id,
                project_id,
                COALESCE(section, '') AS section,
                COALESCE(task_name, title, 'task') AS task_name,
                planned_finish,
                planned_date,
                status,
                is_closed
            FROM kg_entries
            WHERE project_id = ?
              AND NOT (COALESCE(is_closed, 0) = 1 OR status IN ('done', 'closed'))
            ORDER BY COALESCE(planned_finish, planned_date) ASC
        """
        try:
            async with aiosqlite.connect(settings.sqlite_db_path) as db:
                db.row_factory = aiosqlite.Row
                rows = await db.execute_fetchall(query, (project_id,))
        except Exception:
            return []
        return [dict(row) for row in rows]

    async def _get_project_name(self, project_id: str) -> str:
        query = "SELECT name FROM projects WHERE id = ? LIMIT 1"
        try:
            async with aiosqlite.connect(settings.sqlite_db_path) as db:
                cursor = await db.execute(query, (project_id,))
                row = await cursor.fetchone()
                if row is None:
                    return project_id
                return str(row[0])
        except Exception:
            return project_id

    def _is_closed(self, task: dict) -> bool:
        status = str(task.get("status") or "").lower()
        return bool(task.get("is_closed")) or status in {"done", "closed"}

    def _delay_days(self, task: dict) -> int:
        planned = self._parse_date(task.get("planned_finish") or task.get("planned_date"))
        actual = self._parse_date(task.get("actual_finish") or task.get("actual_date"))
        if planned is None or actual is None:
            return 0
        return (actual - planned).days

    def _parse_date(self, value: object) -> dt.date | None:
        if value is None:
            return None
        if isinstance(value, dt.datetime):
            return value.date()
        if isinstance(value, dt.date):
            return value
        text = str(value)
        if not text:
            return None
        candidates = [text, text.replace("Z", "+00:00")]
        for candidate in candidates:
            try:
                return dt.datetime.fromisoformat(candidate).date()
            except ValueError:
                continue
        try:
            return dt.date.fromisoformat(text[:10])
        except ValueError:
            return None

    def _parse_json_object(self, content: str) -> dict | None:
        text = content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text.removeprefix("json").strip()
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
            return None
        except json.JSONDecodeError:
            return None
