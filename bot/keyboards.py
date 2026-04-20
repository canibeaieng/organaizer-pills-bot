from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💊 Добавить лекарство")],
        [KeyboardButton(text="📋 Мои лекарства")],
        [KeyboardButton(text="✏️ Редактировать лекарства")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие",
)


def reminder_answer_keyboard(followup_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Выпил", callback_data=f"followup:{followup_id}:yes")],
            [InlineKeyboardButton(text="⏰ Напомнить через 15 минут", callback_data=f"followup:{followup_id}:no")],
        ]
    )


def edit_medications_keyboard(items: list[tuple[int, str, str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for medication_id, name, dosage, time_of_day in items:
        label = f"💊 {name} — {dosage} в {time_of_day}"
        builder.button(text=label[:64], callback_data=f"edit_med:{medication_id}")

    builder.adjust(1)
    return builder.as_markup()


def edit_medication_actions_keyboard(medication_id: int, name: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Изменить название", callback_data=f"edit_field:{medication_id}:name")
    builder.button(text="💉 Изменить дозировку", callback_data=f"edit_field:{medication_id}:dosage")
    builder.button(text="🕐 Изменить время", callback_data=f"edit_field:{medication_id}:time")
    builder.button(text="🗑️ Удалить", callback_data=f"delete_med:{medication_id}")
    builder.button(text="◀️ Назад", callback_data="back_to_edit_list")
    builder.adjust(1)
    return builder.as_markup()
