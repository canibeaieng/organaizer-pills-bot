from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


MAIN_MENU = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Добавить лекарство")],
        [KeyboardButton(text="Посмотреть лекарства")],
        [KeyboardButton(text="Редактировать лекарства")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие",
)


CONFIRMATION_MENU = InlineKeyboardMarkup(
    inline_keyboard=[
        [InlineKeyboardButton(text="Да", callback_data="confirm_yes")],
        [InlineKeyboardButton(text="Нет (напомнить через 15 минут)", callback_data="confirm_no")],
    ]
)



def reminder_answer_keyboard(followup_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да", callback_data=f"followup:{followup_id}:yes")],
            [InlineKeyboardButton(text="Нет (напомнить через 15 минут)", callback_data=f"followup:{followup_id}:no")],
        ]
    )



def edit_medications_keyboard(items: list[tuple[int, str, str, str]]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()

    for medication_id, name, dosage, time_of_day in items:
        label = f"Удалить: {name} ({dosage}, {time_of_day})"
        builder.button(text=label[:64], callback_data=f"delete_med:{medication_id}")

    builder.adjust(1)
    return builder.as_markup()
