from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import aiosqlite


@dataclass(slots=True)
class Medication:
    id: int
    user_id: int
    name: str
    dosage: str
    time_of_day: str


@dataclass(slots=True)
class Followup:
    id: int
    user_id: int
    medication_id: int
    due_at: datetime


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def init(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS medications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    dosage TEXT NOT NULL,
                    time_of_day TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS reminder_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medication_id INTEGER NOT NULL,
                    reminder_date TEXT NOT NULL,
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(medication_id, reminder_date)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS followups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    medication_id INTEGER NOT NULL,
                    due_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.commit()

    async def add_medication(self, user_id: int, name: str, dosage: str, time_of_day: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO medications (user_id, name, dosage, time_of_day)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, name.strip(), dosage.strip(), time_of_day.strip()),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_user_medications(self, user_id: int) -> list[Medication]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT id, user_id, name, dosage, time_of_day
                FROM medications
                WHERE user_id = ? AND is_active = 1
                ORDER BY time_of_day, id
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()

        return [Medication(*row) for row in rows]

    async def get_medication_by_id(self, medication_id: int) -> Medication | None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT id, user_id, name, dosage, time_of_day
                FROM medications
                WHERE id = ? AND is_active = 1
                """,
                (medication_id,),
            )
            row = await cursor.fetchone()

        return Medication(*row) if row else None

    async def update_medication_field(self, user_id: int, medication_id: int, field: str, value: str) -> bool:
        allowed_fields = {"name", "dosage", "time_of_day"}
        if field not in allowed_fields:
            return False
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                f"UPDATE medications SET {field} = ? WHERE id = ? AND user_id = ? AND is_active = 1",
                (value, medication_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def delete_medication(self, user_id: int, medication_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE medications
                SET is_active = 0
                WHERE id = ? AND user_id = ? AND is_active = 1
                """,
                (medication_id, user_id),
            )
            await db.execute(
                """
                UPDATE followups
                SET status = 'cancelled'
                WHERE medication_id = ? AND user_id = ? AND status IN ('pending', 'awaiting')
                """,
                (medication_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def get_due_medications(self, hh_mm: str) -> list[Medication]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT id, user_id, name, dosage, time_of_day
                FROM medications
                WHERE is_active = 1 AND time_of_day = ?
                """,
                (hh_mm,),
            )
            rows = await cursor.fetchall()

        return [Medication(*row) for row in rows]

    async def mark_daily_reminder_sent(self, medication_id: int, reminder_date: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    """
                    INSERT INTO reminder_log (medication_id, reminder_date)
                    VALUES (?, ?)
                    """,
                    (medication_id, reminder_date),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def create_followup(self, user_id: int, medication_id: int, due_at: datetime) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                INSERT INTO followups (user_id, medication_id, due_at)
                VALUES (?, ?, ?)
                """,
                (user_id, medication_id, due_at.isoformat()),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def get_due_followups(self, now: datetime) -> list[Followup]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT id, user_id, medication_id, due_at
                FROM followups
                WHERE status IN ('pending', 'awaiting') AND due_at <= ?
                ORDER BY due_at ASC
                """,
                (now.isoformat(),),
            )
            rows = await cursor.fetchall()

        return [
            Followup(id=row[0], user_id=row[1], medication_id=row[2], due_at=datetime.fromisoformat(row[3]))
            for row in rows
        ]

    async def get_followup(self, followup_id: int) -> Followup | None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT id, user_id, medication_id, due_at
                FROM followups
                WHERE id = ?
                """,
                (followup_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return Followup(id=row[0], user_id=row[1], medication_id=row[2], due_at=datetime.fromisoformat(row[3]))

    async def get_followup_status(self, followup_id: int) -> str | None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT status FROM followups WHERE id = ?
                """,
                (followup_id,),
            )
            row = await cursor.fetchone()

        return row[0] if row else None

    async def get_latest_open_followup_for_user(self, user_id: int) -> Followup | None:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT id, user_id, medication_id, due_at
                FROM followups
                WHERE user_id = ? AND status IN ('pending', 'awaiting')
                ORDER BY due_at DESC, id DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = await cursor.fetchone()

        if not row:
            return None

        return Followup(id=row[0], user_id=row[1], medication_id=row[2], due_at=datetime.fromisoformat(row[3]))

    async def complete_followup(self, followup_id: int) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE followups
                SET status = 'done'
                WHERE id = ?
                """,
                (followup_id,),
            )
            await db.commit()

    async def is_followup_pending(self, followup_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT 1 FROM followups WHERE id = ? AND status IN ('pending', 'awaiting')
                """,
                (followup_id,),
            )
            row = await cursor.fetchone()

        return row is not None

    async def mark_followup_sent(self, followup_id: int, next_due_at: datetime) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE followups
                SET status = 'awaiting', due_at = ?
                WHERE id = ? AND status IN ('pending', 'awaiting')
                """,
                (next_due_at.isoformat(), followup_id),
            )
            await db.commit()
