from datetime import date, datetime, timedelta, timezone
from typing import Annotated, Literal
from pydantic import AwareDatetime, Field, PlainSerializer, field_validator
from app.enums.mission_enum import MissionCategory
from app.enums.schedule_enum import ScheduleType
from app.schema.common_schema import BaseDTO

KST = timezone(timedelta(hours=9)) # UTC+9

# 시각은 KST(+09:00)로 내려준다
KstDateTime = Annotated[datetime, PlainSerializer(lambda v: v.astimezone(KST), return_type=datetime)]

# 기분 3단계 (임의 결정 D-32: 4~5 good, 3 neutral, 1~2 bad)
MoodLevel = Literal["good", "neutral", "bad"]


# ===== 월 달력 =====

# 하루 칸
class CalendarDaySummaryDTO(BaseDTO):
    date: date
    mood_score: int | None = None       # 마음 날씨 1~5 (기록 없으면 null)
    mood_level: MoodLevel | None = None # 기분 캐릭터 단계
    has_diary: bool                     # 일기를 쓴 날
    goal_completed: int                 # 완료한 일일목표 수
    goal_total: int                     # 사용 중인 일일목표 수
    has_hospital_visit: bool            # 병원 가는 날 (진료 예약·검사 일정)
    schedule_count: int                 # 그날 시작하는 일정 수


# 월 달력
class CalendarMonthResponseDTO(BaseDTO):
    month: str          # 2026-11
    today: date         # 오늘 (KST) - 오늘 칸 강조용
    days: list[CalendarDaySummaryDTO]  # 그 달의 모든 날짜


# ===== 날짜 상세 =====

# 그날 기분
class CalendarMoodDTO(BaseDTO):
    score: int
    level: MoodLevel
    tag: str | None = None


# 일일목표 1개
class CalendarGoalDTO(BaseDTO):
    mission_id: int
    name: str
    description: str | None = None
    category: MissionCategory | None = None  # body: 몸 / habit: 습관 / mind: 마음
    reward_point: int
    target_count: int        # 목표 횟수 (물 6잔이면 6)
    progress_count: int      # 그날 진행 횟수
    completed: bool
    completed_at: KstDateTime | None = None


# 그날 일일목표
class CalendarGoalsDTO(BaseDTO):
    completed: int
    total: int
    items: list[CalendarGoalDTO]


# 그날 일기 (일기 화면으로 이동용)
class CalendarDiaryDTO(BaseDTO):
    diary_id: int
    preview: str             # 앞부분 (임의 결정 D-37)
    updated_at: KstDateTime | None = None


# 일정 1개
class CalendarScheduleDTO(BaseDTO):
    schedule_id: int
    schedule_type: ScheduleType   # counseling·appointment·exam·notice·personal
    title: str
    memo: str | None = None
    start_at: KstDateTime
    end_at: KstDateTime | None = None
    remind_at: KstDateTime | None = None
    appointment_id: int | None = None  # 진료 예약 일정이면 예약 id
    editable: bool                     # 내 개인 일정만 true (임의 결정 D-35)


# 날짜 상세
class CalendarDayDetailResponseDTO(BaseDTO):
    date: date
    is_today: bool
    mood: CalendarMoodDTO | None = None
    goals: CalendarGoalsDTO
    diary: CalendarDiaryDTO | None = None
    schedules: list[CalendarScheduleDTO]  # 시작 시각순


# ===== 개인 일정 (일정-05) =====

# 앞뒤 공백 제거, 빈 제목 거절
def _strip_title(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("제목을 입력하세요.")
    return value


# 개인 일정 등록 (시각은 +09:00 같은 시간대를 꼭 붙인다)
class PersonalScheduleCreateDTO(BaseDTO):
    title: str = Field(max_length=100)
    start_at: AwareDatetime
    end_at: AwareDatetime | None = None
    memo: str | None = Field(default=None, max_length=255)
    remind_at: AwareDatetime | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        return _strip_title(value)


# 개인 일정 수정 (보낸 값만 수정: model_dump(exclude_unset=True))
# - 끝 시각·메모·알림을 지우려면 null을 보낸다.
class PersonalScheduleUpdateDTO(BaseDTO):
    title: str | None = Field(default=None, max_length=100)
    start_at: AwareDatetime | None = None
    end_at: AwareDatetime | None = None
    memo: str | None = Field(default=None, max_length=255)
    remind_at: AwareDatetime | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        return _strip_title(value)
