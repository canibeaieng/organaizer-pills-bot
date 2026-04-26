from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from bot.db import Database
from bot.keyboards import reminder_answer_keyboard, restock_purchase_keyboard

logger = logging.getLogger(__name__)

DAILY_REPORT_TIME = "21:00"
MONTHLY_REPORT_TIME = "21:00"
RESTOCK_REMINDER_TIME = "10:00"
RU_MONTH_NAMES = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


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

            followup_time = now + timedelta(minutes=15)
            followup_id = await self.db.create_followup(
                user_id=medication.user_id,
                medication_id=medication.id,
                due_at=followup_time,
            )

            await self.bot.send_message(
                chat_id=medication.user_id,
                text=(
                    "Напоминаю о приеме лекарства!\n"
                    f"{medication.name}, {medication.dosage}\n"
                    f"Время: {medication.time_of_day}\n\n"
                    "Отметь ответ кнопкой ниже: выпил или не выпил"
                ),
                reply_markup=reminder_answer_keyboard(followup_id),
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
                    "Нажми кнопку ниже. Если кнопки не видно, ответь сообщением: Да или Нет\n"
                    "Если не ответишь, я снова напомню через 30 минут"
                ),
                reply_markup=reminder_answer_keyboard(followup.id),
            )
            await self.db.mark_followup_sent(followup.id, now + timedelta(minutes=30))

        await self._send_restock_reminders(now, current_hhmm, current_date)
        await self._send_daily_reports(now, current_hhmm, current_date)
        await self._send_monthly_reports(now, current_hhmm, current_date)

    async def _send_restock_reminders(self, now: datetime, current_hhmm: str, current_date: str) -> None:
        if current_hhmm != RESTOCK_REMINDER_TIME:
            return

        medications = await self.db.get_restock_medications()
        for medication in medications:
            inserted = await self.db.mark_restock_reminder_sent(medication.id, current_date)
            if not inserted:
                continue

            await self.bot.send_message(
                chat_id=medication.user_id,
                text=(
                    "🛒 <b>Пора купить лекарство</b>\n\n"
                    f"💊 {medication.name}\n"
                    f"💉 {medication.dosage}\n\n"
                    "Нажми кнопку ниже, когда купишь его. Пока лекарство не куплено, обычные напоминания по нему на паузе."
                ),
                reply_markup=restock_purchase_keyboard(medication.id),
                parse_mode="HTML",
            )

    async def _send_daily_reports(self, now: datetime, current_hhmm: str, current_date: str) -> None:
        if current_hhmm != DAILY_REPORT_TIME:
            return

        user_ids = await self.db.get_report_user_ids()
        for user_id in user_ids:
            inserted = await self.db.mark_report_sent(user_id, "daily", current_date)
            if not inserted:
                continue

            summary = await self.db.get_daily_taken_summary(user_id, current_date)
            total_taken = sum(count for _, count in summary)
            lines = [
                f"📊 <b>Ежедневный отчёт</b>",
                f"Сегодня {self._format_date_verbose(now)}.",
                f"✅ Подтверждённых приёмов: <b>{total_taken}</b>",
            ]

            if summary:
                lines.append("")
                lines.append("Что было принято:")
                for medication_name, count in summary:
                    lines.append(f"• {medication_name} — {count} раз")
            else:
                lines.append("")
                lines.append("Сегодня подтверждённых приёмов пока не было.")

            await self.bot.send_message(
                chat_id=user_id,
                text="\n".join(lines),
                parse_mode="HTML",
            )

    async def _send_monthly_reports(self, now: datetime, current_hhmm: str, current_date: str) -> None:
        if current_hhmm != MONTHLY_REPORT_TIME or now.day != 29:
            return

        month_key = now.strftime("%Y-%m")
        start_date = now.replace(day=1).strftime("%Y-%m-%d")
        user_ids = await self.db.get_report_user_ids()
        for user_id in user_ids:
            inserted = await self.db.mark_report_sent(user_id, "monthly", month_key)
            if not inserted:
                continue

            scheduled_total, taken_total, breakdown = await self.db.get_monthly_summary(user_id, start_date, current_date)
            missed_total = max(scheduled_total - taken_total, 0)
            lines = [
                f"🗓️ <b>Отчёт за месяц</b>",
                f"Статистика за {now.day} {RU_MONTH_NAMES[now.month]} {now.year}.",
                f"✅ Принято: <b>{taken_total}</b>",
                f"❌ Упущено: <b>{missed_total}</b>",
            ]

            if breakdown:
                lines.append("")
                lines.append("По лекарствам:")
                for medication_name, taken_count, missed_count in breakdown:
                    lines.append(f"• {medication_name} — принято {taken_count}, упущено {missed_count}")

            await self.bot.send_message(
                chat_id=user_id,
                text="\n".join(lines),
                parse_mode="HTML",
            )

    def _format_date_verbose(self, now: datetime) -> str:
        return f"{now.day} {RU_MONTH_NAMES[now.month]} {now.year}"
