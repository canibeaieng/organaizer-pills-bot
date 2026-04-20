from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from bot.db import Database
from bot.keyboards import reminder_answer_keyboard

logger = logging.getLogger(__name__)


class ReminderScheduler:
    def __init__(self, bot: Bot, db: Database, timezone: ZoneInfo) -> None:
        self.bot = bot
        self.db = db
        self.timezone = timezone
        self._task: asyncio.Task[None] | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="reminder_scheduler")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except Exception:
                logger.exception("Ошибка в планировщике напоминаний")
            await asyncio.sleep(20)

    async def _tick(self) -> None:
        now = datetime.now(self.timezone)
        current_hhmm = now.strftime("%H:%M")
        current_date = now.strftime("%Y-%m-%d")

        due_medications = await self.db.get_due_medications(current_hhmm)
        for medication in due_medications:
            inserted = await self.db.mark_daily_reminder_sent(medication.id, current_date)
            if not inserted:
                continue

            await self.bot.send_message(
                chat_id=medication.user_id,
                text=(
                    "Напоминаю о приеме лекарства!\n"
                    f"{medication.name}, {medication.dosage}\n"
                    f"Время: {medication.time_of_day}"
                ),
            )
            followup_time = now + timedelta(minutes=30)
            await self.db.create_followup(
                user_id=medication.user_id,
                medication_id=medication.id,
                due_at=followup_time,
            )

        due_followups = await self.db.get_due_followups(now)
        for followup in due_followups:
            medication = await self.db.get_medication_by_id(followup.medication_id)
            if medication is None:
                await self.db.complete_followup(followup.id)
                continue

            await self.bot.send_message(
                chat_id=followup.user_id,
                text=(
                    "Ты выпил лекарство?\n"
                    f"{medication.name}, {medication.dosage}\n\n"
                    "Нажми кнопку ниже. Если кнопки не видно, ответь сообщением: Да или Нет"
                ),
                reply_markup=reminder_answer_keyboard(followup.id),
            )
            await self.db.mark_followup_sent(followup.id)
