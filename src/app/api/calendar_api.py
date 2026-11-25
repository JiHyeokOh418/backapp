from datetime import date
from fastapi import APIRouter, Depends, Query, status
from app.service.calendar_service import get_calendar_service, CalendarService
from app.schema.user_schema import UserClaimDTO
from app.schema.calendar_schema import (
    CalendarMonthResponseDTO,
    CalendarDayDetailResponseDTO,
    CalendarScheduleDTO,
    PersonalScheduleCreateDTO,
    PersonalScheduleUpdateDTO,
)
from app.schema.common_schema import ApiResponseDTO
from app.dependencie.auth_dependency import get_current_user


# 환자 캘린더 (Figma: MyPage/Calendar, 화면-08, 기록-09, 일정-05)
# - main.py에서 prefix="/calendar"로 등록한다.
# - 로그인한 사용자 본인의 기록·일정만 다룬다.
router = APIRouter()


# Swagger 문서용 공통 에러 응답
def error_example(description: str, detail: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"example": {"detail": detail}}}
    }

SCHEDULE_NOT_FOUND = error_example("일정 없음 또는 남의 일정", "일정이 존재하지 않습니다.")
NOT_PERSONAL = error_example("병원에서 등록한 일정", "병원에서 등록한 일정은 바꿀 수 없습니다.")
BAD_TIME = error_example("시각 오류", "끝 시각은 시작 시각보다 뒤여야 합니다.")


# 1. 월 달력
@router.get(
    "",
    summary="월 달력 (날짜별 기분·일기·일일목표·병원 가는 날)",
    response_model=ApiResponseDTO[CalendarMonthResponseDTO]
)
async def get_month(
    month: str | None = Query(default=None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM (없으면 이번 달)"),
    current_user: UserClaimDTO = Depends(get_current_user),
    calendar_service: CalendarService = Depends(get_calendar_service)
):
    calendar = await calendar_service.get_month(current_user.id, month)

    return ApiResponseDTO(
        success=True,
        message="월 달력 조회 완료",
        data=calendar
    )


# 2. 날짜 상세
@router.get(
    "/days/{day}",
    summary="날짜 상세 (그날 기분·일일목표·일기·일정)",
    response_model=ApiResponseDTO[CalendarDayDetailResponseDTO]
)
async def get_day(
    day: date,
    current_user: UserClaimDTO = Depends(get_current_user),
    calendar_service: CalendarService = Depends(get_calendar_service)
):
    detail = await calendar_service.get_day(current_user.id, day)

    return ApiResponseDTO(
        success=True,
        message="날짜 상세 조회 완료",
        data=detail
    )


# 3. 개인 일정 등록 (오른쪽 위 + 버튼)
@router.post(
    "/schedules",
    summary="개인 일정 등록",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[CalendarScheduleDTO],
    responses={400: BAD_TIME}
)
async def create_schedule(
    request: PersonalScheduleCreateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    calendar_service: CalendarService = Depends(get_calendar_service)
):
    schedule = await calendar_service.create_schedule(current_user.id, request)

    return ApiResponseDTO(
        success=True,
        message="개인 일정 등록 완료",
        data=schedule
    )


# 4. 개인 일정 수정 (보낸 값만 수정)
@router.put(
    "/schedules/{schedule_id}",
    summary="개인 일정 수정",
    response_model=ApiResponseDTO[CalendarScheduleDTO],
    responses={400: BAD_TIME, 403: NOT_PERSONAL, 404: SCHEDULE_NOT_FOUND}
)
async def update_schedule(
    schedule_id: int,
    request: PersonalScheduleUpdateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    calendar_service: CalendarService = Depends(get_calendar_service)
):
    schedule = await calendar_service.update_schedule(current_user.id, schedule_id, request)

    return ApiResponseDTO(
        success=True,
        message="개인 일정 수정 완료",
        data=schedule
    )


# 5. 개인 일정 삭제
@router.delete(
    "/schedules/{schedule_id}",
    summary="개인 일정 삭제",
    response_model=ApiResponseDTO,
    responses={403: NOT_PERSONAL, 404: SCHEDULE_NOT_FOUND}
)
async def delete_schedule(
    schedule_id: int,
    current_user: UserClaimDTO = Depends(get_current_user),
    calendar_service: CalendarService = Depends(get_calendar_service)
):
    await calendar_service.delete_schedule(current_user.id, schedule_id)

    return ApiResponseDTO(
        success=True,
        message="개인 일정 삭제 완료"
    )
