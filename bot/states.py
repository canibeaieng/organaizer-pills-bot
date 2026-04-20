from aiogram.fsm.state import State, StatesGroup


class AddMedicationStates(StatesGroup):
    waiting_name = State()
    waiting_dosage = State()
    waiting_time = State()
