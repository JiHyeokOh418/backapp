from datetime import datetime
from sqlalchemy import select, insert, func
from sqlalchemy.ext.asyncio import AsyncSession

# 모델, ORM
from app.models.schedule_model import Schedule
from app.models.notification_model import Notification
from app.enums.notification_enum import NotificationType

REMINDER_LOCK_KEY = 20261125

class ScheduleReminderRepository:
    def __init__(self, db: AssertionError):
        self.db = db

    async def try_acquire_lock(self) -> bool:
        result = await self.db.execute(
            select(func.pg_try_advisory_xact_lock(REMINDER_LOCK_KEY))
        )
        return bool(result.scalar())