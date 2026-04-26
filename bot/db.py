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
                    needs_restock INTEGER NOT NULL DEFAULT 0,
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
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS medication_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    medication_id INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    event_date TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS report_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    report_type TEXT NOT NULL,
                    period_key TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, report_type, period_key)
                )
                """
            )
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS restock_reminder_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    medication_id INTEGER NOT NULL,
                    reminder_date TEXT NOT NULL,
                    sent_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(medication_id, reminder_date)
                )
                """
            )
            cursor = await db.execute("PRAGMA table_info(medications)")
            medication_columns = {row[1] for row in await cursor.fetchall()}
            if "needs_restock" not in medication_columns:
                await db.execute(
                    """
                    ALTER TABLE medications
                    ADD COLUMN needs_restock INTEGER NOT NULL DEFAULT 0
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
                WHERE is_active = 1 AND needs_restock = 0 AND time_of_day = ?
                """,
                (hh_mm,),
            )
            rows = await cursor.fetchall()

        return [Medication(*row) for row in rows]

    async def get_restock_medications(self) -> list[Medication]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT id, user_id, name, dosage, time_of_day
                FROM medications
                WHERE is_active = 1 AND needs_restock = 1
                ORDER BY user_id, name, id
                """
            )
            rows = await cursor.fetchall()

        return [Medication(*row) for row in rows]

    async def get_report_user_ids(self) -> list[int]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT DISTINCT user_id
                FROM medications
                WHERE is_active = 1
                ORDER BY user_id
                """
            )
            rows = await cursor.fetchall()

        return [int(row[0]) for row in rows]

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

    async def add_medication_event(
        self,
        user_id: int,
        medication_id: int,
        event_type: str,
        event_date: str,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO medication_events (user_id, medication_id, event_type, event_date)
                VALUES (?, ?, ?, ?)
                """,
                (user_id, medication_id, event_type, event_date),
            )
            await db.commit()

    async def mark_restock_requested(self, user_id: int, medication_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE medications
                SET needs_restock = 1
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

    async def mark_restock_completed(self, user_id: int, medication_id: int) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                UPDATE medications
                SET needs_restock = 0
                WHERE id = ? AND user_id = ? AND is_active = 1
                """,
                (medication_id, user_id),
            )
            await db.commit()
            return cursor.rowcount > 0

    async def mark_restock_reminder_sent(self, medication_id: int, reminder_date: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    """
                    INSERT INTO restock_reminder_log (medication_id, reminder_date)
                    VALUES (?, ?)
                    """,
                    (medication_id, reminder_date),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def mark_report_sent(self, user_id: int, report_type: str, period_key: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    """
                    INSERT INTO report_log (user_id, report_type, period_key)
                    VALUES (?, ?, ?)
                    """,
                    (user_id, report_type, period_key),
                )
                await db.commit()
                return True
            except aiosqlite.IntegrityError:
                return False

    async def get_daily_taken_summary(self, user_id: int, event_date: str) -> list[tuple[str, int]]:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT m.name, COUNT(*)
                FROM medication_events e
                JOIN medications m ON m.id = e.medication_id
                WHERE e.user_id = ? AND e.event_type = 'taken' AND e.event_date = ? AND m.is_active = 1
                GROUP BY m.name
                ORDER BY m.name ASC
                """,
                (user_id, event_date),
            )
            rows = await cursor.fetchall()

        return [(str(row[0]), int(row[1])) for row in rows]

    async def get_monthly_summary(
        self,
        user_id: int,
        start_date: str,
        end_date: str,
    ) -> tuple[int, int, list[tuple[str, int, int]]]:
        async with aiosqlite.connect(self.db_path) as db:
            scheduled_cursor = await db.execute(
                """
                SELECT COUNT(*)
                FROM reminder_log r
                JOIN medications m ON m.id = r.medication_id
                WHERE m.user_id = ? AND m.is_active = 1 AND r.reminder_date BETWEEN ? AND ?
                """,
                (user_id, start_date, end_date),
            )
            scheduled_total = int((await scheduled_cursor.fetchone())[0])

            taken_cursor = await db.execute(
                """
                SELECT COUNT(*)
                FROM medication_events e
                JOIN medications m ON m.id = e.medication_id
                WHERE e.user_id = ? AND e.event_type = 'taken' AND e.event_date BETWEEN ? AND ? AND m.is_active = 1
                """,
                (user_id, start_date, end_date),
            )
            taken_total = int((await taken_cursor.fetchone())[0])

            scheduled_breakdown_cursor = await db.execute(
                """
                SELECT m.id, m.name, COUNT(r.id)
                FROM medications m
                LEFT JOIN reminder_log r
                    ON r.medication_id = m.id AND r.reminder_date BETWEEN ? AND ?
                WHERE m.user_id = ? AND m.is_active = 1
                GROUP BY m.id, m.name
                HAVING COUNT(r.id) > 0
                """,
                (start_date, end_date, user_id),
            )
            scheduled_rows = await scheduled_breakdown_cursor.fetchall()

            taken_breakdown_cursor = await db.execute(
                """
                SELECT m.id, m.name, COUNT(e.id)
                FROM medications m
                LEFT JOIN medication_events e
                    ON e.medication_id = m.id
                    AND e.user_id = m.user_id
                    AND e.event_type = 'taken'
                    AND e.event_date BETWEEN ? AND ?
                WHERE m.user_id = ? AND m.is_active = 1
                GROUP BY m.id, m.name
                HAVING COUNT(e.id) > 0
                """,
                (start_date, end_date, user_id),
            )
            taken_rows = await taken_breakdown_cursor.fetchall()

        stats_by_medication: dict[int, dict[str, int | str]] = {}
        for medication_id, name, scheduled_count in scheduled_rows:
            stats_by_medication[int(medication_id)] = {
                "name": str(name),
                "scheduled": int(scheduled_count),
                "taken": 0,
            }

        for medication_id, name, taken_count in taken_rows:
            entry = stats_by_medication.setdefault(
                int(medication_id),
                {"name": str(name), "scheduled": 0, "taken": 0},
            )
            entry["taken"] = int(taken_count)

        breakdown: list[tuple[str, int, int]] = []
        for entry in sorted(stats_by_medication.values(), key=lambda item: str(item["name"])):
            breakdown.append(
                (
                    str(entry["name"]),
                    int(entry["taken"]),
                    max(int(entry["scheduled"]) - int(entry["taken"]), 0),
                )
            )

        return scheduled_total, taken_total, breakdown

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
