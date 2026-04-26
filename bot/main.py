from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.db import Database
from bot.keyboards import MAIN_MENU, edit_medication_actions_keyboard, edit_medications_keyboard, restock_purchase_keyboard
from bot.scheduler import ReminderScheduler
from bot.states import AddMedicationStates, EditMedicationStates


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


dp = Dispatcher()
db = Database("data/medications.db")
APP_TIMEZONE = None
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


def _local_now() -> datetime:
    return datetime.now(APP_TIMEZONE) if APP_TIMEZONE is not None else datetime.now().astimezone()


def _format_verbose_date(now: datetime) -> str:
    return f"{now.day} {RU_MONTH_NAMES[now.month]} {now.year}"


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    name = message.from_user.first_name if message.from_user else "друг"
    await message.answer(
        f"👋 Привет, {name}! Я помогу не забывать принимать лекарства.\n"
        "Используй кнопки меню ниже 👇",
        reply_markup=MAIN_MENU,
    )


@dp.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "ℹ️ <b>Справка</b>\n\n"
        "Команды:\n"
        "/start — перезапустить меню\n"
        "/help — помощь\n\n"
        "Кнопки:\n"
        "💊 Добавить лекарство\n"
        "📋 Мои лекарства\n"
        "📊 Статистика\n"
        "✏️ Редактировать лекарства",
        parse_mode="HTML",
    )


@dp.message(F.text == "💊 Добавить лекарство")
async def add_medication_begin(message: Message, state: FSMContext) -> None:
    await state.set_state(AddMedicationStates.waiting_name)
    await message.answer("💊 Введите название лекарства.\nНапример: <b>Витамин D</b>", parse_mode="HTML")


@dp.message(AddMedicationStates.waiting_name)
async def add_medication_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Название слишком короткое. Введите еще раз.")
        return

    await state.update_data(name=name)
    await state.set_state(AddMedicationStates.waiting_dosage)
    await message.answer("💉 Введите дозировку.\nНапример: <b>1 капсула</b>", parse_mode="HTML")


@dp.message(AddMedicationStates.waiting_dosage)
async def add_medication_dosage(message: Message, state: FSMContext) -> None:
    dosage = (message.text or "").strip()
    if len(dosage) < 1:
        await message.answer("Дозировка не должна быть пустой. Введите еще раз.")
        return

    await state.update_data(dosage=dosage)
    await state.set_state(AddMedicationStates.waiting_time)
    await message.answer("🕐 Введите время приема в формате ЧЧ:ММ.\nНапример: <b>17:00</b>", parse_mode="HTML")


@dp.message(AddMedicationStates.waiting_time)
async def add_medication_time(message: Message, state: FSMContext) -> None:
    time_of_day = (message.text or "").strip()
    if TIME_PATTERN.match(time_of_day) is None:
        await message.answer("❌ Неверный формат времени. Используйте ЧЧ:ММ, например <b>07:30</b>", parse_mode="HTML")
        return

    data = await state.get_data()
    user_id = message.from_user.id if message.from_user else 0
    medication_id = await db.add_medication(
        user_id=user_id,
        name=data["name"],
        dosage=data["dosage"],
        time_of_day=time_of_day,
    )
    await state.clear()

    user_medications = await db.get_user_medications(user_id)
    user_med_number = len(user_medications)

    await message.answer(
        "✅ <b>Лекарство добавлено!</b>\n\n"
        f"📌 Номер в вашем списке: {user_med_number}\n"
        f"💊 {data['name']} — {data['dosage']}\n"
        f"🕐 Напоминание: {time_of_day}",
        reply_markup=MAIN_MENU,
        parse_mode="HTML",
    )


@dp.message(F.text == "📋 Мои лекарства")
async def list_medications(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    medications = await db.get_user_medications(user_id)

    if not medications:
        await message.answer("📭 Список пуст. Сначала добавьте лекарство.")
        return

    lines = ["📋 <b>Ваши лекарства:</b>\n"]
    for idx, item in enumerate(medications, start=1):
        lines.append(f"{idx}. 💊 <b>{item.name}</b> — {item.dosage}\n    🕐 {item.time_of_day}")

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(F.text == "📊 Статистика")
async def show_statistics(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    now = _local_now()
    current_date = now.strftime("%Y-%m-%d")
    month_start = now.replace(day=1).strftime("%Y-%m-%d")

    daily_summary = await db.get_daily_taken_summary(user_id, current_date)
    scheduled_total, taken_total, monthly_breakdown = await db.get_monthly_summary(user_id, month_start, current_date)
    missed_total = max(scheduled_total - taken_total, 0)

    lines = [
        "📊 <b>Статистика</b>",
        "",
        f"Сегодня, {_format_verbose_date(now)}:",
        f"✅ Подтверждено приёмов: <b>{sum(count for _, count in daily_summary)}</b>",
    ]

    if daily_summary:
        for medication_name, count in daily_summary:
            lines.append(f"• {medication_name} — {count} раз")
    else:
        lines.append("• Сегодня подтверждённых приёмов пока нет")

    lines.extend(
        [
            "",
            f"За текущий месяц ({now.strftime('%m.%Y')}):",
            f"✅ Принято: <b>{taken_total}</b>",
            f"❌ Упущено: <b>{missed_total}</b>",
        ]
    )

    if monthly_breakdown:
        for medication_name, taken_count, missed_count in monthly_breakdown:
            lines.append(f"• {medication_name} — принято {taken_count}, упущено {missed_count}")
    else:
        lines.append("• За текущий месяц статистики пока нет")

    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(F.text == "✏️ Редактировать лекарства")
async def edit_medications(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    medications = await db.get_user_medications(user_id)

    if not medications:
        await message.answer("📭 Пока нет активных лекарств для редактирования.")
        return

    rows = [(item.id, item.name, item.dosage, item.time_of_day) for item in medications]
    await message.answer(
        "✏️ <b>Выберите лекарство для редактирования:</b>",
        reply_markup=edit_medications_keyboard(rows),
        parse_mode="HTML",
    )


@dp.callback_query(F.data.startswith("edit_med:"))
async def edit_medication_select(callback: CallbackQuery) -> None:
    if not callback.data:
        return

    _, medication_id_text = callback.data.split(":", 1)
    try:
        medication_id = int(medication_id_text)
    except ValueError:
        await callback.answer("Некорректный ID", show_alert=True)
        return

    medication = await db.get_medication_by_id(medication_id)
    if not medication or medication.user_id != callback.from_user.id:
        await callback.answer("Лекарство не найдено", show_alert=True)
        return

    await callback.message.edit_text(
        f"💊 <b>{medication.name}</b>\n"
        f"💉 Дозировка: {medication.dosage}\n"
        f"🕐 Время: {medication.time_of_day}\n\n"
        "Что хотите изменить?",
        reply_markup=edit_medication_actions_keyboard(medication.id, medication.name),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "back_to_edit_list")
async def back_to_edit_list(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    medications = await db.get_user_medications(user_id)

    if not medications:
        await callback.message.edit_text("📭 Пока нет активных лекарств.")
        await callback.answer()
        return

    rows = [(item.id, item.name, item.dosage, item.time_of_day) for item in medications]
    await callback.message.edit_text(
        "✏️ <b>Выберите лекарство для редактирования:</b>",
        reply_markup=edit_medications_keyboard(rows),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("edit_field:"))
async def edit_field_select(callback: CallbackQuery, state: FSMContext) -> None:
    if not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    _, medication_id_text, field = parts
    try:
        medication_id = int(medication_id_text)
    except ValueError:
        await callback.answer("Некорректный ID", show_alert=True)
        return

    medication = await db.get_medication_by_id(medication_id)
    if not medication or medication.user_id != callback.from_user.id:
        await callback.answer("Лекарство не найдено", show_alert=True)
        return

    prompts = {
        "name": "📝 Введите новое название лекарства:",
        "dosage": "💉 Введите новую дозировку:",
        "time": "🕐 Введите новое время приема в формате ЧЧ:ММ (например: <b>08:00</b>):",
    }
    db_field = "time_of_day" if field == "time" else field

    await state.set_state(EditMedicationStates.waiting_new_value)
    await state.update_data(medication_id=medication_id, field=db_field)
    await callback.message.edit_text(prompts[field], parse_mode="HTML")
    await callback.answer()


@dp.message(EditMedicationStates.waiting_new_value)
async def edit_field_value(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    medication_id: int = data["medication_id"]
    field: str = data["field"]
    value = (message.text or "").strip()
    user_id = message.from_user.id if message.from_user else 0

    if field == "time_of_day":
        if TIME_PATTERN.match(value) is None:
            await message.answer("❌ Неверный формат времени. Используйте ЧЧ:ММ, например <b>07:30</b>", parse_mode="HTML")
            return
    elif len(value) < 1:
        await message.answer("❌ Значение не может быть пустым. Попробуйте ещё раз.")
        return

    updated = await db.update_medication_field(user_id, medication_id, field, value)
    await state.clear()

    if updated:
        field_names = {"name": "Название", "dosage": "Дозировка", "time_of_day": "Время приема"}
        await message.answer(
            f"✅ <b>{field_names.get(field, 'Поле')} обновлено!</b>\n"
            f"Новое значение: <b>{value}</b>",
            reply_markup=MAIN_MENU,
            parse_mode="HTML",
        )
    else:
        await message.answer("❌ Не удалось обновить. Возможно, лекарство уже удалено.", reply_markup=MAIN_MENU)


@dp.callback_query(F.data.startswith("delete_med:"))
async def delete_medication_callback(callback: CallbackQuery) -> None:
    if not callback.data:
        return

    _, medication_id_text = callback.data.split(":", 1)
    try:
        medication_id = int(medication_id_text)
    except ValueError:
        await callback.answer("Некорректный ID", show_alert=True)
        return

    user_id = callback.from_user.id
    removed = await db.delete_medication(user_id, medication_id)
    if removed:
        await callback.message.edit_text("🗑️ Лекарство удалено.")
        await callback.answer("Удалено")
    else:
        await callback.answer("❌ Не удалось удалить или запись уже неактивна", show_alert=True)


async def _process_followup_action(user_id: int, followup_id: int, action: str) -> tuple[bool, str]:
    if action not in {"yes", "no", "restock"}:
        return False, "Неизвестное действие"

    if not await db.is_followup_pending(followup_id):
        return False, "Этот вопрос уже закрыт"

    followup = await db.get_followup(followup_id)
    if followup is None:
        return False, "Вопрос не найден"

    if followup.user_id != user_id:
        return False, "Этот вопрос не для вас"

    medication = await db.get_medication_by_id(followup.medication_id)
    await db.complete_followup(followup_id)
    event_date = _local_now().strftime("%Y-%m-%d")

    if action == "yes":
        await db.add_medication_event(user_id, followup.medication_id, "taken", event_date)
        return True, "🎉 Отлично! Лекарство принято, отметил ✅"

    if action == "restock":
        updated = await db.mark_restock_requested(user_id, followup.medication_id)
        if not updated:
            return False, "Не удалось включить напоминание о покупке"
        await db.add_medication_event(user_id, followup.medication_id, "restock_requested", event_date)
        med_text = "лекарство"
        if medication:
            med_text = medication.name
        return True, f"🛒 Принято. По {med_text} теперь будут приходить напоминания купить лекарство"

    now = _local_now()
    next_time = now + timedelta(minutes=15)
    await db.create_followup(
        user_id=followup.user_id,
        medication_id=followup.medication_id,
        due_at=next_time,
    )
    med_text = "лекарство"
    if medication:
        med_text = f"{medication.name} ({medication.dosage})"

    return True, f"⏰ Хорошо, напомню через 15 минут: {med_text}"


@dp.callback_query(F.data.startswith("followup:"))
async def followup_answer_callback(callback: CallbackQuery, bot: Bot) -> None:
    if not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    _, followup_id_text, action = parts
    try:
        followup_id = int(followup_id_text)
    except ValueError:
        await callback.answer("Некорректный ID", show_alert=True)
        return

    ok, user_message = await _process_followup_action(callback.from_user.id, followup_id, action)
    if not ok:
        await callback.answer(user_message, show_alert=True)
        return

    await callback.answer("Готово")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(user_message)


@dp.callback_query(F.data.startswith("restock:"))
async def restock_done_callback(callback: CallbackQuery) -> None:
    if not callback.data:
        return

    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Некорректные данные", show_alert=True)
        return

    _, medication_id_text, action = parts
    if action != "done":
        await callback.answer("Неизвестное действие", show_alert=True)
        return

    try:
        medication_id = int(medication_id_text)
    except ValueError:
        await callback.answer("Некорректный ID", show_alert=True)
        return

    medication = await db.get_medication_by_id(medication_id)
    if medication is None or medication.user_id != callback.from_user.id:
        await callback.answer("Лекарство не найдено", show_alert=True)
        return

    updated = await db.mark_restock_completed(callback.from_user.id, medication_id)
    if not updated:
        await callback.answer("Не удалось обновить статус", show_alert=True)
        return

    await db.add_medication_event(callback.from_user.id, medication_id, "restock_completed", _local_now().strftime("%Y-%m-%d"))
    await callback.answer("Отлично")
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(
            f"✅ Лекарство <b>{medication.name}</b> снова в наличии. Обычные напоминания возобновлены.",
            parse_mode="HTML",
        )


@dp.message(F.text.regexp(r"(?i)^(да|нет)$"))
async def followup_text_answer(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    latest_followup = await db.get_latest_open_followup_for_user(user_id)

    if latest_followup is None:
        return

    action = "yes" if (message.text or "").strip().lower() == "да" else "no"
    ok, user_message = await _process_followup_action(user_id, latest_followup.id, action)
    if not ok:
        await message.answer(user_message)
        return

    await message.answer(user_message)


@dp.message()
async def fallback_handler(message: Message) -> None:
    await message.answer(
        "🤔 Я не понял команду. Используйте кнопки меню ниже.",
        reply_markup=MAIN_MENU,
    )


async def main() -> None:
    global APP_TIMEZONE
    settings = load_settings()
    APP_TIMEZONE = settings.timezone
    bot = Bot(token=settings.bot_token)

    await db.init()

    scheduler = ReminderScheduler(bot=bot, db=db, timezone=settings.timezone)
    await scheduler.start()

    try:
        await dp.start_polling(bot)
    finally:
        await scheduler.stop()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
