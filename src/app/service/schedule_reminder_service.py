import asyncio
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.repository.schedule_reminder_repository import ScheduleReminderRepository
from app.enums.notification_enum import NotificationType
from app.schema.schedule_reminder_schema import (
    ScheduleReminderTargetDTO,
    ScheduleReminderRunResultDTO,
)
from app.util.date_util import KST

logger = logging.getLogger(__name__)

TITLE_MAX_LENGTH = 100

WEEKDAYS = "월화수목금토일"

def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit - 1] + "…"


def _format_start(start_at: datetime) -> str:
    start = start_at.astimezone(KST)
    return f"{start.month}월 {start.day}일 ({WEEKDAYS[start.weekday()]}) {start:%H:%M}"


class ScheduleReminderService:

    def __init__(self, repo: ScheduleReminderRepository):
        self.repo = repo

    
    @staticmethod
    def _build_notification(target: ScheduleReminderTargetDTO, now: datetime):
        return {
            "user_id": target.user_id,
            "schedule_id": target.schedule_id,
            "notification_type": NotificationType.SCHEDULE,
            "title": _truncate(f"일정 알림: {target.title}", TITLE_MAX_LENGTH),
            "content": f"{_format_start(target.start_at)}에 시작하는 일정이에요.",
            "sent_at": now,
        }
    
    async def run_once(self, now: datetime | None = None) -> ScheduleReminderRunResultDTO:
        now =  now or datetime.now(KST)

        if not await self.repo.try_acquire_lock():
            return ScheduleReminderRunResultDTO(
                lock_acquired=False, checked_count=0, created_count=0
            )
        
        schedules = await self.repo.find_due_schedules(now)
        targets = [ScheduleReminderTargetDTO.model_validate(s) for s in schedules]
        rows = [self._build_notification(target, now) for target in targets]
        created_count = await self.repo.create_notifications(rows)

        return ScheduleReminderRunResultDTO(
            lock_acquired=True,
            checked_count=len(targets),
            created_count=created_count
        )
    
    async def run_schedule_reminder_loop(
        session_factory: async_sessionmaker[AsyncSession],
        interval_seconds: int = 60
    ) -> None:
        while True:
            try: 
                async with session_factory() as db:
                    service = ScheduleReminderService(ScheduleReminderRepository(db))
                    result = await service.run_once()

                if result.created_count > 0:
                    print(f"일정 알림 {result.created_count}건 생성")

            except Exception:
                logger.exception("일정알림 스케줄러 실행 중 오류")

            await asyncio.sleep(interval_seconds)


