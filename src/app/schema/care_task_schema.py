from app.schema.common_schema import BaseDTO
from datetime import date, datetime
from app.enums.mission_enum import MissionCategory
# 오늘의 작은 돌봄 / 나만의 돌봄 (미션과 같은 개념으로 묶어서 처리) 요청/응답 DTO
# 규칙: BaseDTO 상속, XxxCreateDTO / XxxUpdateDTO / XxxResponseDTO 이름 사용

# TODO: DTO 추가

#일일목표(화면; 홈 일일목표, 오늘의 일일 목표, 오늘의 작은 돌봅)
class CareTaskItemResponseDTO(BaseDTO):
    mission_id: int 
    description: str | None=None    
    category:MissionCategory | None=None    #body, habit, mind
    reward_point: int
    target_count: int   # 물 마시기는 6, 나머지는 1
    progress_count: int #오늘 진행("ex) 지금까지 3잔")
    is_auto: bool   #True면 기록했을 때 자동 완료 -> 앱은 해당 화면으로 이동만
    is_completed: bool  # True-> 오늘 한 일, False-> 해 볼 만한 것
    is_completed_at:datetime | None=None

#오늘 할 일 화면 전체
class TodayCareTaskResponseDTO(BaseDTO):
    today: date
    mission: list[CareTaskItemResponseDTO]
    completed_count: int #2/3 에서 2
    total_count: int    #2/3에서 3
    bonus_received: bool
    earned_today: int   #오늘 모은 포인트
    daily_cap: int  # 하루 최대 60p

#체크/체크 취소 결과
class CareTaskCheckResponseDTO(BaseDTO):
    mission_id: int
    progress_count: int
    is_completed: bool
    changed_point: int  # 이번에 받은 포인트 +, 취소된 포인트 -, 없으면 0
    bonus_changed: int  # 보너스 지급 +10, 취소 -10, 없으면 0
    earned_today: int
    completed_count: int

#이번 주 돌아보기 - 하루. -> 오늘의 일일목표 화면 아래에 있는 막대그래프 부분
class WeeklyDayResponseDTO(BaseDTO):
    day: date
    completed_count: int

# 이번 주 돌아보기 - 월요일 ~ 일요일 7개. -> 그 그래프 전체
class WeeklyCareTaskResponseDTO(BaseDTO):
    days: list[WeeklyDayResponseDTO]
    total_count: int    #하루 목표 수(막대 높이 기준)

#포인트 모으는법 (포인트샵 '모으는 법'버튼)
class MissionGuideResponseDTO(BaseDTO):
    mission_id: int
    name: str
    reward_point: int
    daily_limit: int
    is_auto: bool