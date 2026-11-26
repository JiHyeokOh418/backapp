from datetime import datetime, timedelta, timezone
from typing import Annotated
from pydantic import PlainSerializer
from app.schema.common_schema import BaseDTO

KST = timezone(timedelta(hours=9)) # UTC+9

# 시각은 KST(+09:00)로 내려준다 (calendar_schema.py와 같은 방식)
KstDateTime = Annotated[datetime, PlainSerializer(lambda v: v.astimezone(KST), return_type=datetime)]


class ScheduleReminderTargetDTO(BaseDTO):
    schedule_id: int
    user_id: int            # 알림을 받는 환자 (schedules.user_id)
    title: str              # 일정 제목
    start_at: KstDateTime   # 일정 시작 시각
    remind_at: KstDateTime  # 알림 시각


# 스케줄러 1회 실행 결과 (로그·테스트 확인용)
class ScheduleReminderRunResultDTO(BaseDTO):
    lock_acquired : bool # 다른 워커가 실행 중이라 건너뛰었으면 False
    checked_count: int  # 이번 실행에서 대상으로 조회된 일정 수
    created_count: int  # 알림을 실제로 만든 수
