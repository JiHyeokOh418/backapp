from datetime import datetime
from sqlalchemy import select, insert, func
from sqlalchemy.ext.asyncio import AsyncSession

# 모델, ORM
from app.models.schedule_model import Schedule
from app.models.notification_model import Notification
from app.enums.notification_enum import NotificationType

# 스케줄러 중복 실행 방지용 advisory lock 번호 (앱 안에서 겹치지 않는 임의의 정수)
REMINDER_LOCK_KEY = 20261125


class ScheduleReminderRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db


    # 1. 이번 실행을 맡을 수 있는지 확인 (다른 워커가 이미 실행 중이면 False)
    # - 트랜잭션이 끝나면(commit·세션 종료) 잠금도 자동으로 풀린다.
    # - 조회·저장·commit까지 같은 세션에서 이어서 해야 잠금이 유지된다.
    async def try_acquire_lock(self) -> bool:
        result = await self.db.execute(
            select(func.pg_try_advisory_xact_lock(REMINDER_LOCK_KEY))
        )
        return bool(result.scalar())


    # 2. 알림을 보내야 하는 일정 조회
    # - 알림 시각이 지났고(remind_at <= now), 일정이 아직 시작 전이고(start_at > now)
    # - 같은 일정에 'schedule' 알림이 아직 없는 것
    # - 진료 예약에서 생긴 일정(appointment_id 있음)은 예약 기능 담당이라 뺀다.
    # - now를 밖에서 받는다 (테스트에서 시각을 고정할 수 있다)
    # - 서버가 꺼져 있던 동안 놓친 알림도 같은 조건으로 잡힌다.
    # - user_ids: 특정 사용자만 대상으로 돌릴 때 쓴다 (테스트용). None이면 전체.
    async def find_due_schedules(
        self, now: datetime, limit: int = 500, user_ids: list[int] | None = None
    ) -> list[Schedule]:
        has_alert = (
            select(Notification.notification_id)
            .where(
                Notification.schedule_id == Schedule.schedule_id,
                Notification.notification_type == NotificationType.SCHEDULE
            )
            .exists()
        )

        conditions = [
            Schedule.remind_at.is_not(None),
            Schedule.remind_at <= now,
            Schedule.start_at > now,
            Schedule.appointment_id.is_(None),
            ~has_alert
        ]

        if user_ids is not None:
            conditions.append(Schedule.user_id.in_(user_ids))

        query = (
            select(Schedule)
            .where(*conditions)
            .order_by(Schedule.remind_at, Schedule.schedule_id)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 3. 알림 여러 건 저장
    # - rows의 각 dict는 같은 키를 가져야 한다:
    #   user_id, schedule_id, notification_type, title, content, sent_at
    # - commit은 여기서 한다 (잠금도 이때 풀린다)
    async def create_notifications(self, rows: list[dict]) -> int:
        if not rows:
            return 0

        await self.db.execute(insert(Notification), rows)
        await self.db.commit()
        return len(rows)
