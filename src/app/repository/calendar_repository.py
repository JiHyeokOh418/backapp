from datetime import date, datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.postgresql import get_postgresql_db
from fastapi import Depends

# 모델, ORM
from app.models.emotion_record_model import EmotionRecord
from app.models.diary_model import Diary
from app.models.mission_model import Mission
from app.models.user_mission_log_model import UserMissionLog
from app.models.schedule_model import Schedule
from app.enums.mission_enum import MissionType
from app.enums.schedule_enum import ScheduleType
from sqlalchemy import select, insert, update, delete

KST = timezone(timedelta(hours=9)) # UTC+9


class CalendarRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db


    # 1. 감정 기록 (날짜 [start, end), 삭제 제외)
    # - 환자 본인 화면이라 is_shared(의사 공유 여부)는 보지 않는다. (임의 결정 D-32)
    async def find_emotion_records(self, user_id: int, start: date, end: date) -> list[EmotionRecord]:
        query = (
            select(EmotionRecord)
            .where(
                EmotionRecord.user_id == user_id,
                EmotionRecord.deleted_at.is_(None),
                EmotionRecord.record_date >= start,
                EmotionRecord.record_date < end
            )
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 2. 일기 (시각 [start_at, end_at), 삭제 제외, 날짜순)
    async def find_diaries(self, user_id: int, start_at: datetime, end_at: datetime) -> list[Diary]:
        query = (
            select(Diary)
            .where(
                Diary.user_id == user_id,
                Diary.deleted_at.is_(None),
                Diary.diary_date >= start_at,
                Diary.diary_date < end_at
            )
            .order_by(Diary.diary_date, Diary.diary_id)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 3. 사용 중인 일일목표 (표시 순서대로, 모두 완료 보너스는 제외) - 임의 결정 D-31
    async def find_daily_goals(self) -> list[Mission]:
        query = (
            select(Mission)
            .where(
                Mission.mission_type == MissionType.DAILY_GOAL,
                Mission.is_active.is_(True)
            )
            .order_by(Mission.sort_order, Mission.mission_id)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 4. 일일목표 수행 기록 (날짜 [start, end), mission_ids 안의 목표만)
    async def find_mission_logs(
        self, user_id: int, mission_ids: list[int], start: date, end: date
    ) -> list[UserMissionLog]:
        if not mission_ids:
            return []

        query = (
            select(UserMissionLog)
            .where(
                UserMissionLog.user_id == user_id,
                UserMissionLog.mission_id.in_(mission_ids),
                UserMissionLog.log_date >= start,
                UserMissionLog.log_date < end
            )
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 5. 일정 (시작 시각 [start_at, end_at), 시작 시각순)
    async def find_schedules(self, user_id: int, start_at: datetime, end_at: datetime) -> list[Schedule]:
        query = (
            select(Schedule)
            .where(
                Schedule.user_id == user_id,
                Schedule.start_at >= start_at,
                Schedule.start_at < end_at
            )
            .order_by(Schedule.start_at, Schedule.schedule_id)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 6. 일정 1건
    # - populate_existing: 수정 직후 다시 조회할 때 DB 값으로 덮어쓴다.
    async def find_schedule(self, schedule_id: int) -> Schedule | None:
        query = (
            select(Schedule)
            .where(Schedule.schedule_id == schedule_id)
            .execution_options(populate_existing=True)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 7. 개인 일정 등록 -> 새 일정 id
    async def create_personal_schedule(self, user_id: int, values: dict) -> int:
        now = datetime.now(KST)
        result = await self.db.execute(
            insert(Schedule)
            .values(
                user_id=user_id,
                created_by=user_id,
                schedule_type=ScheduleType.PERSONAL,
                created_at=now,
                **values
            )
            .returning(Schedule.schedule_id)
        )
        schedule_id = result.scalar_one()
        await self.db.commit()
        return schedule_id


    # 8. 개인 일정 수정 (내 개인 일정일 때만) -> 바뀌었으면 True
    async def update_personal_schedule(self, user_id: int, schedule_id: int, values: dict) -> bool:
        result = await self.db.execute(
            update(Schedule)
            .where(
                Schedule.schedule_id == schedule_id,
                Schedule.user_id == user_id,
                Schedule.schedule_type == ScheduleType.PERSONAL
            )
            .values(**values, updated_at=datetime.now(KST))
        )
        await self.db.commit()
        return result.rowcount > 0


    # 9. 개인 일정 삭제 (내 개인 일정일 때만) -> 지웠으면 True
    async def delete_personal_schedule(self, user_id: int, schedule_id: int) -> bool:
        result = await self.db.execute(
            delete(Schedule)
            .where(
                Schedule.schedule_id == schedule_id,
                Schedule.user_id == user_id,
                Schedule.schedule_type == ScheduleType.PERSONAL
            )
        )
        await self.db.commit()
        return result.rowcount > 0



# 주입 팩토리 메서드
def get_calendar_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return CalendarRepository(db)
