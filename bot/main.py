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
from bot.keyboards import MAIN_MENU, edit_medications_keyboard
from bot.scheduler import ReminderScheduler
from bot.states import AddMedicationStates


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


dp = Dispatcher()
db = Database("data/medications.db")
APP_TIMEZONE = None


@dp.message(CommandStart())
async def start_handler(message: Message) -> None:
    await message.answer(
        "Привет! Я помогу не забывать принимать лекарства.\n"
        "Используй кнопки меню ниже.",
        reply_markup=MAIN_MENU,
    )


@dp.message(Command("help"))
async def help_handler(message: Message) -> None:
    await message.answer(
        "Команды:\n"
        "/start - перезапустить меню\n"
        "/help - помощь\n\n"
        "Кнопки:\n"
        "Добавить лекарство\n"
        "Посмотреть лекарства\n"
        "Редактировать лекарства"
    )


@dp.message(F.text == "Добавить лекарство")
async def add_medication_begin(message: Message, state: FSMContext) -> None:
    await state.set_state(AddMedicationStates.waiting_name)
    await message.answer("Введите название лекарства. Например: Витамин D")


@dp.message(AddMedicationStates.waiting_name)
async def add_medication_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 2:
        await message.answer("Название слишком короткое. Введите еще раз.")
        return

    await state.update_data(name=name)
    await state.set_state(AddMedicationStates.waiting_dosage)
    await message.answer("Введите дозировку. Например: 1 капсула")


@dp.message(AddMedicationStates.waiting_dosage)
async def add_medication_dosage(message: Message, state: FSMContext) -> None:
    dosage = (message.text or "").strip()
    if len(dosage) < 1:
        await message.answer("Дозировка не должна быть пустой. Введите еще раз.")
        return

    await state.update_data(dosage=dosage)
    await state.set_state(AddMedicationStates.waiting_time)
    await message.answer("Введите время приема в формате ЧЧ:ММ. Например: 17:00")


@dp.message(AddMedicationStates.waiting_time)
async def add_medication_time(message: Message, state: FSMContext) -> None:
    time_of_day = (message.text or "").strip()
    if TIME_PATTERN.match(time_of_day) is None:
        await message.answer("Неверный формат времени. Используйте ЧЧ:ММ, например 07:30")
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
        "Лекарство добавлено.\n"
        f"Номер в вашем списке: {user_med_number}\n"
        f"{data['name']} - {data['dosage']} - {time_of_day}",
        reply_markup=MAIN_MENU,
    )


@dp.message(F.text == "Посмотреть лекарства")
async def list_medications(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    medications = await db.get_user_medications(user_id)

    if not medications:
        await message.answer("Список пуст. Сначала добавьте лекарство.")
        return

    lines = ["Текущие лекарства:"]
    for idx, item in enumerate(medications, start=1):
        lines.append(f"{idx}. {item.name} - {item.dosage} - {item.time_of_day}")

    await message.answer("\n".join(lines))


@dp.message(F.text == "Редактировать лекарства")
async def edit_medications(message: Message) -> None:
    user_id = message.from_user.id if message.from_user else 0
    medications = await db.get_user_medications(user_id)

    if not medications:
        await message.answer("Пока нет активных лекарств для редактирования.")
        return

    rows = [(item.id, item.name, item.dosage, item.time_of_day) for item in medications]
    await message.answer(
        "Выберите лекарство, которое нужно удалить:",
        reply_markup=edit_medications_keyboard(rows),
    )


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
        await callback.message.edit_text("Лекарство удалено.")
        await callback.answer("Удалено")
    else:
        await callback.answer("Не удалось удалить или запись уже неактивна", show_alert=True)


async def _process_followup_action(user_id: int, followup_id: int, action: str) -> tuple[bool, str]:
    if action not in {"yes", "no"}:
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

    if action == "yes":
        return True, "Супер! Отметил, что лекарство принято."

    now = datetime.now(APP_TIMEZONE) if APP_TIMEZONE is not None else datetime.now().astimezone()
    next_time = now + timedelta(minutes=15)
    await db.create_followup(
        user_id=followup.user_id,
        medication_id=followup.medication_id,
        due_at=next_time,
    )
    med_text = "лекарство"
    if medication:
        med_text = f"{medication.name} ({medication.dosage})"

    return True, f"Принято. Напомню через 15 минут: {med_text}"


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
        "Я не понял команду. Используйте кнопки меню.",
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
