from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from fastapi import Depends, HTTPException, status
from app.repository.calendar_repository import CalendarRepository, get_calendar_repository
from app.models.emotion_record_model import EmotionRecord
from app.models.diary_model import Diary
from app.models.mission_model import Mission
from app.models.user_mission_log_model import UserMissionLog
from app.models.schedule_model import Schedule
from app.enums.schedule_enum import ScheduleType
from app.schema.calendar_schema import (
    MoodLevel,
    CalendarDaySummaryDTO,
    CalendarMonthResponseDTO,
    CalendarMoodDTO,
    CalendarGoalDTO,
    CalendarGoalsDTO,
    CalendarDiaryDTO,
    CalendarScheduleDTO,
    CalendarDayDetailResponseDTO,
    PersonalScheduleCreateDTO,
    PersonalScheduleUpdateDTO,
)
from app.util.date_util import KST, kst_day_range, today_kst, month_range

# 병원 가는 날로 표시하는 일정 종류 (임의 결정 D-33)
HOSPITAL_SCHEDULE_TYPES = (ScheduleType.APPOINTMENT, ScheduleType.EXAM)

# 일기 미리보기 길이 (임의 결정 D-37)
DIARY_PREVIEW_LENGTH = 50


# 마음 날씨 1~5 -> 기분 캐릭터 3단계 (임의 결정 D-32)
def mood_level(score: int) -> MoodLevel:
    if score >= 4:
        return "good"
    if score == 3:
        return "neutral"
    return "bad"


# 목표 완료 = 완료 시각이 있고 취소되지 않음 (임의 결정 D-30)
def is_completed(log: UserMissionLog) -> bool:
    return log.completed_at is not None and log.canceled_at is None


# 기간 [first_day, next_day)의 캘린더 재료를 날짜별로 묶은 것
@dataclass
class CalendarData:
    goals: list[Mission]
    moods: dict[date, EmotionRecord] = field(default_factory=dict)
    diaries: dict[date, Diary] = field(default_factory=dict)
    logs: dict[date, dict[int, UserMissionLog]] = field(default_factory=dict)  # 날짜 -> 목표 id -> 기록
    schedules: dict[date, list[Schedule]] = field(default_factory=dict)


# 예외처리, 서비스가 드러나도록 이름을 선정해서 제작
# 트랜잭션 관리
class CalendarService:

    def __init__(self, repo: CalendarRepository):
        self.repo = repo

    # TODO: 서비스 메서드 추가

def get_calendar_service(repo: CalendarRepository = Depends(get_calendar_repository)) -> CalendarService:

    # 기간의 기분·일기·목표 기록·일정을 한 번씩 조회해서 날짜별로 묶는다 (쿼리 5번)
    async def _collect(self, user_id: int, first_day: date, next_day: date) -> CalendarData:
        start_at, end_at = kst_day_range(first_day)[0], kst_day_range(next_day)[0]

        goals = await self.repo.find_daily_goals()
        data = CalendarData(goals=goals)

        for record in await self.repo.find_emotion_records(user_id, first_day, next_day):
            data.moods[record.record_date] = record

        # 일기는 날짜마다 1개 (같은 날 여러 개면 마지막 것)
        for diary in await self.repo.find_diaries(user_id, start_at, end_at):
            data.diaries[diary.diary_date.astimezone(KST).date()] = diary

        for log in await self.repo.find_mission_logs(user_id, [g.mission_id for g in goals], first_day, next_day):
            data.logs.setdefault(log.log_date, {})[log.mission_id] = log

        # 일정은 시작 날짜에만 표시 (임의 결정 D-34)
        for schedule in await self.repo.find_schedules(user_id, start_at, end_at):
            data.schedules.setdefault(schedule.start_at.astimezone(KST).date(), []).append(schedule)

        return data


    # ORM -> 일정 DTO (내 개인 일정만 수정 가능)
    @staticmethod
    def _to_schedule(schedule: Schedule) -> CalendarScheduleDTO:
        return CalendarScheduleDTO(
            schedule_id=schedule.schedule_id,
            schedule_type=schedule.schedule_type,
            title=schedule.title,
            memo=schedule.memo,
            start_at=schedule.start_at,
            end_at=schedule.end_at,
            remind_at=schedule.remind_at,
            appointment_id=schedule.appointment_id,
            editable=schedule.schedule_type == ScheduleType.PERSONAL
        )


    # 1. 월 달력 (기록-09)
    async def get_month(self, user_id: int, month: str | None) -> CalendarMonthResponseDTO:
        today = today_kst()
        month = month or today.strftime("%Y-%m")
        first_day, next_day = month_range(month)
        data = await self._collect(user_id, first_day, next_day)

        days = []
        for offset in range((next_day - first_day).days):
            day = first_day + timedelta(days=offset)
            mood = data.moods.get(day)
            day_schedules = data.schedules.get(day, [])
            days.append(CalendarDaySummaryDTO(
                date=day,
                mood_score=mood.mood_score if mood else None,
                mood_level=mood_level(mood.mood_score) if mood else None,
                has_diary=day in data.diaries,
                goal_completed=sum(is_completed(log) for log in data.logs.get(day, {}).values()),
                goal_total=len(data.goals),
                has_hospital_visit=any(s.schedule_type in HOSPITAL_SCHEDULE_TYPES for s in day_schedules),
                schedule_count=len(day_schedules)
            ))

        return CalendarMonthResponseDTO(month=month, today=today, days=days)


    # 2. 날짜 상세 (그날 기분, 일일목표 진행, 일기, 일정)
    async def get_day(self, user_id: int, day: date) -> CalendarDayDetailResponseDTO:
        data = await self._collect(user_id, day, day + timedelta(days=1))
        logs = data.logs.get(day, {})

        goals = []
        for goal in data.goals:
            log = logs.get(goal.mission_id)
            goals.append(CalendarGoalDTO(
                mission_id=goal.mission_id,
                name=goal.name,
                description=goal.description,
                category=goal.category,
                reward_point=goal.reward_point,
                target_count=goal.target_count,
                progress_count=log.progress_count if log else 0,
                completed=bool(log) and is_completed(log),
                completed_at=log.completed_at if log and is_completed(log) else None
            ))

        mood = data.moods.get(day)
        diary = data.diaries.get(day)

        return CalendarDayDetailResponseDTO(
            date=day,
            is_today=day == today_kst(),
            mood=CalendarMoodDTO(score=mood.mood_score, level=mood_level(mood.mood_score), tag=mood.mood_tag) if mood else None,
            goals=CalendarGoalsDTO(completed=sum(g.completed for g in goals), total=len(goals), items=goals),
            diary=CalendarDiaryDTO(
                diary_id=diary.diary_id,
                preview=diary.content[:DIARY_PREVIEW_LENGTH],
                updated_at=diary.updated_at or diary.created_at
            ) if diary else None,
            schedules=[self._to_schedule(s) for s in data.schedules.get(day, [])]
        )


    # ===== 개인 일정 (일정-05, 결정-23) =====

    # 시각 확인: 끝 > 시작, 알림 < 시작 (임의 결정 D-36)
    @staticmethod
    def _check_times(start_at: datetime, end_at: datetime | None, remind_at: datetime | None) -> None:
        if end_at is not None and end_at <= start_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="끝 시각은 시작 시각보다 뒤여야 합니다."
            )

        if remind_at is not None and remind_at >= start_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="알림 시각은 시작 시각보다 앞이어야 합니다."
            )


    # 내 일정인지 확인 - 없거나 남의 일정이면 404, 병원이 등록한 일정이면 403 (임의 결정 D-35)
    async def _get_my_personal_schedule(self, user_id: int, schedule_id: int) -> Schedule:
        schedule = await self.repo.find_schedule(schedule_id)
        if not schedule or schedule.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="일정이 존재하지 않습니다."
            )

        if schedule.schedule_type != ScheduleType.PERSONAL:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="병원에서 등록한 일정은 바꿀 수 없습니다."
            )

        return schedule


    # 3. 개인 일정 등록
    async def create_schedule(self, user_id: int, request: PersonalScheduleCreateDTO) -> CalendarScheduleDTO:
        self._check_times(request.start_at, request.end_at, request.remind_at)

        schedule_id = await self.repo.create_personal_schedule(user_id, request.model_dump())
        return self._to_schedule(await self.repo.find_schedule(schedule_id))


    # 4. 개인 일정 수정 (보낸 값만, 바뀐 뒤의 시각으로 다시 확인)
    async def update_schedule(
        self, user_id: int, schedule_id: int, request: PersonalScheduleUpdateDTO
    ) -> CalendarScheduleDTO:
        schedule = await self._get_my_personal_schedule(user_id, schedule_id)

        values = request.model_dump(exclude_unset=True)
        for required in ("title", "start_at"):  # 필수 컬럼은 null로 지울 수 없다
            if required in values and values[required] is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"{required}는 비울 수 없습니다."
                )

        self._check_times(
            values.get("start_at", schedule.start_at),
            values.get("end_at", schedule.end_at),
            values.get("remind_at", schedule.remind_at)
        )

        if values:
            await self.repo.update_personal_schedule(user_id, schedule_id, values)

        return self._to_schedule(await self.repo.find_schedule(schedule_id))


    # 5. 개인 일정 삭제
    async def delete_schedule(self, user_id: int, schedule_id: int) -> None:
        await self._get_my_personal_schedule(user_id, schedule_id)
        await self.repo.delete_personal_schedule(user_id, schedule_id)



# 레포지토리 주입 팩토리 함수
def get_calendar_service(repo: CalendarRepository = Depends(get_calendar_repository)):
    return CalendarService(repo)
