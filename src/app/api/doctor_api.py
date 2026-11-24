from datetime import date
from typing import Literal
from fastapi import APIRouter, Depends, Query, status
from app.service.doctor_service import get_doctor_service, DoctorService
from app.schema.user_schema import UserClaimDTO
from app.schema.doctor_schema import (
    DashboardSummaryResponseDTO,
    RoomResponseDTO,
    DoctorPatientResponseDTO,
    DoctorAppointmentResponseDTO,
    RiskEventResponseDTO,
    CalendarResponseDTO,
    AssessmentTrendResponseDTO,
    ChatRecordResponseDTO,
    ChatSessionDetailResponseDTO,
    RiskEventDetailResponseDTO,
    RiskEventActionCreateDTO,
    EmotionReportResponseDTO,
    IntakeResultResponseDTO,
    PatientAppointmentsResponseDTO,
    AppointmentDetailResponseDTO,
    AppointmentCreateDTO,
    AppointmentRescheduleDTO,
    AppointmentCancelDTO,
    AppointmentStatusUpdateDTO,
)
from app.schema.common_schema import ApiResponseDTO, PageRequestDTO, PageResponseDTO
from app.enum.risk_enum import RiskStatus
from app.enum.common_enum import Instrument
from app.dependencie.auth_dependency import get_current_doctor


# 의사 메인 (Figma: Doctormanagechart, API 명세 F-02)
# - main.py에서 prefix="/doctor"로 등록한다.
# - 1단계: 환자 선택과 상관없는 위젯 (요약 바, 진료실, 환자 목록, 오늘 예약, 위험 알림, 월 캘린더)
# - 2단계: 왼쪽에서 환자를 고르면 바뀌는 위젯 (경과 그래프, AI 상담 기록)
#   프론트는 고른 patientId만 바꿔서 같은 API를 다시 부르면 된다.
router = APIRouter()


# Swagger 문서용 공통 에러 응답
def error_example(description: str, detail: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"example": {"detail": detail}}}
    }

NOT_DOCTOR = error_example("의사가 아님", "get_current_doctor 의사만 사용할 수 있습니다.")
NOT_IN_CHARGE = error_example("의사가 아니거나 담당 환자가 아님", "담당 환자가 아닙니다.")

# YYYY-MM (월 캘린더, 환자별 예약)
MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


# 1. 상단 요약 바
@router.get(
    "/dashboard/summary",
    summary="오늘 요약 (예약·완료·대기·위험 알림 수)",
    response_model=ApiResponseDTO[DashboardSummaryResponseDTO],
    responses={403: NOT_DOCTOR}
)
async def get_dashboard_summary(
    date: date | None = Query(default=None, description="기준 날짜 (없으면 오늘, KST)"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    summary = await doctor_service.get_dashboard_summary(current_doctor.id, date)

    return ApiResponseDTO(
        success=True,
        message="오늘 요약 조회 완료",
        data=summary
    )


# 2. 진료실 목록
@router.get(
    "/rooms",
    summary="진료실 목록 (내 소속 병원)",
    response_model=ApiResponseDTO[list[RoomResponseDTO]],
    responses={
        403: NOT_DOCTOR,
        404: error_example("의사 프로필 없음", "의사 프로필이 없습니다.")
    }
)
async def get_rooms(
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    rooms = await doctor_service.get_rooms(current_doctor.id)

    return ApiResponseDTO(
        success=True,
        message="진료실 목록 조회 완료",
        data=rooms
    )


# 3. 환자 목록·검색 (의사-01)
# - 담당 중인 환자만, 위험도 높은 순
@router.get(
    "/patients",
    summary="담당 환자 목록·검색",
    response_model=ApiResponseDTO[list[DoctorPatientResponseDTO]],
    responses={403: NOT_DOCTOR}
)
async def get_patients(
    tab: Literal["all", "waiting", "booked"] = Query(default="all", description="all: 전체 / waiting: 대기 / booked: 예약"),
    date: date | None = Query(default=None, description="예약 기준 날짜 (없으면 오늘, KST)"),
    q: str | None = Query(default=None, max_length=50, description="환자 이름 검색"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    patients = await doctor_service.get_patients(current_doctor.id, tab, date, q)

    return ApiResponseDTO(
        success=True,
        message="담당 환자 목록 조회 완료",
        data=patients
    )


# 4. 오늘 예약 일정
@router.get(
    "/appointments",
    summary="오늘 예약 일정",
    response_model=ApiResponseDTO[list[DoctorAppointmentResponseDTO]],
    responses={403: NOT_DOCTOR}
)
async def get_appointments(
    date: date | None = Query(default=None, description="날짜 (없으면 오늘, KST)"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    appointments = await doctor_service.get_appointments(current_doctor.id, date)

    return ApiResponseDTO(
        success=True,
        message="예약 일정 조회 완료",
        data=appointments
    )


# 5. 위험 환자 알림
@router.get(
    "/risk-events",
    summary="위험 환자 알림 목록",
    response_model=ApiResponseDTO[list[RiskEventResponseDTO]],
    responses={403: NOT_DOCTOR}
)
async def get_risk_events(
    status: RiskStatus = Query(default=RiskStatus.OPEN, description="open: 확인 전 / reviewed: 확인함 / escalated: 상향"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    events = await doctor_service.get_risk_events(current_doctor.id, status)

    return ApiResponseDTO(
        success=True,
        message="위험 알림 조회 완료",
        data=events
    )


# 6. 위험 알림 확인 ("확인" 버튼)
@router.post(
    "/risk-events/{event_id}/review",
    summary="위험 알림 확인",
    response_model=ApiResponseDTO[RiskEventResponseDTO],
    responses={
        403: NOT_IN_CHARGE,
        404: error_example("알림 없음", "위험 알림이 존재하지 않습니다."),
        409: error_example("이미 확인한 알림", "이미 확인한 알림입니다.")
    }
)
async def review_risk_event(
    event_id: int,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    event = await doctor_service.review_risk_event(current_doctor.id, event_id)

    return ApiResponseDTO(
        success=True,
        message="위험 알림 확인 완료",
        data=event
    )


# 7. 월 캘린더
@router.get(
    "/calendar",
    summary="월 캘린더 (날짜별 진료·검사 수)",
    response_model=ApiResponseDTO[CalendarResponseDTO],
    responses={403: NOT_DOCTOR}
)
async def get_calendar(
    month: str | None = Query(default=None, pattern=MONTH_PATTERN, description="YYYY-MM (없으면 이번 달)"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    calendar = await doctor_service.get_calendar(current_doctor.id, month)

    return ApiResponseDTO(
        success=True,
        message="월 캘린더 조회 완료",
        data=calendar
    )


# ===== 2단계: 환자를 고르면 바뀌는 위젯 (담당 환자만) =====

# 8. 경과 그래프 (의사-02·03)
@router.get(
    "/patients/{patient_id}/assessments",
    summary="경과 그래프 (척도 점수 추이)",
    response_model=ApiResponseDTO[AssessmentTrendResponseDTO],
    responses={403: NOT_IN_CHARGE}
)
async def get_assessment_trend(
    patient_id: int,
    instrument: Instrument = Query(default=Instrument.PHQ9, description="척도 (phq9·gad7·isi·bdi2)"),
    months: int = Query(default=3, ge=1, le=12, description="최근 몇 개월"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    trend = await doctor_service.get_assessment_trend(current_doctor.id, patient_id, instrument, months)

    return ApiResponseDTO(
        success=True,
        message="경과 그래프 조회 완료",
        data=trend
    )


# 9. AI 상담 기록 위젯 (의사-04·05)
# - 'AI 소견서' 탭은 Figma에 내용이 없어 API를 만들지 않았다. (의사웹-09)
@router.get(
    "/patients/{patient_id}/records",
    summary="AI 상담 기록 위젯 (최근 세션)",
    response_model=ApiResponseDTO[list[ChatRecordResponseDTO]],
    responses={
        403: NOT_IN_CHARGE,
        501: error_example("일기 탭 미정", "일기 탭은 아직 정해지지 않았습니다. (결정-39·40)")
    }
)
async def get_records(
    patient_id: int,
    tab: Literal["chat", "diary"] = Query(default="chat", description="chat: AI 상담 / diary: 일기 (미정)"),
    limit: int = Query(default=4, ge=1, le=20, description="가져올 개수 (위젯은 4개, 전체는 상담 내역 팝업)"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    records = await doctor_service.get_records(current_doctor.id, patient_id, tab, limit)

    return ApiResponseDTO(
        success=True,
        message="AI 상담 기록 조회 완료",
        data=records
    )


# ===== F-06 AI 상담 내역 팝업 (Figma: Doctor_detailCounsil, 의사-04·05) =====

# 10. 상담 세션 목록
@router.get(
    "/patients/{patient_id}/chat-sessions",
    summary="상담 세션 목록 (상담 내역 팝업)",
    response_model=ApiResponseDTO[PageResponseDTO[ChatRecordResponseDTO]],
    responses={403: NOT_IN_CHARGE}
)
async def get_chat_sessions(
    patient_id: int,
    page: PageRequestDTO = Depends(),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    sessions = await doctor_service.get_chat_sessions(current_doctor.id, patient_id, page.offset, page.limit)

    return ApiResponseDTO(
        success=True,
        message="상담 세션 목록 조회 완료",
        data=sessions
    )


# 11. 상담 세션 상세
@router.get(
    "/chat-sessions/{session_id}",
    summary="상담 세션 상세 (요약·감정 변화·대화 전문)",
    response_model=ApiResponseDTO[ChatSessionDetailResponseDTO],
    responses={
        403: NOT_IN_CHARGE,
        404: error_example("세션 없음", "상담 세션이 존재하지 않습니다.")
    }
)
async def get_chat_session_detail(
    session_id: int,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    detail = await doctor_service.get_chat_session_detail(current_doctor.id, session_id)

    return ApiResponseDTO(
        success=True,
        message="상담 세션 상세 조회 완료",
        data=detail
    )


# ===== F-05 위험 감지 상세 팝업 (Figma: Doctor_detailRisk, 의사-06·07) =====

RISK_NOT_FOUND = error_example("알림 없음", "위험 알림이 존재하지 않습니다.")


# 12. 환자별 감지 목록
@router.get(
    "/patients/{patient_id}/risk-events",
    summary="환자별 위험 감지 목록",
    response_model=ApiResponseDTO[list[RiskEventResponseDTO]],
    responses={403: NOT_IN_CHARGE}
)
async def get_patient_risk_events(
    patient_id: int,
    days: int = Query(default=30, ge=1, le=365, description="최근 며칠 (오늘 포함)"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    events = await doctor_service.get_patient_risk_events(current_doctor.id, patient_id, days)

    return ApiResponseDTO(
        success=True,
        message="위험 감지 목록 조회 완료",
        data=events
    )


# 13. 감지 상세
@router.get(
    "/risk-events/{event_id}",
    summary="위험 감지 상세 (앞뒤 대화·걸린 단어·조치 이력)",
    response_model=ApiResponseDTO[RiskEventDetailResponseDTO],
    responses={403: NOT_IN_CHARGE, 404: RISK_NOT_FOUND}
)
async def get_risk_event_detail(
    event_id: int,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    detail = await doctor_service.get_risk_event_detail(current_doctor.id, event_id)

    return ApiResponseDTO(
        success=True,
        message="위험 감지 상세 조회 완료",
        data=detail
    )


# 14. 조치 기록 추가
# - 응답은 갱신된 감지 상세 (상태·조치 이력을 팝업에 바로 다시 그릴 수 있게)
@router.post(
    "/risk-events/{event_id}/actions",
    summary="위험 조치 기록 추가 (note·escalate)",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[RiskEventDetailResponseDTO],
    responses={
        403: NOT_IN_CHARGE,
        404: RISK_NOT_FOUND,
        409: error_example("이미 위기 대응으로 올린 알림", "이미 위기 대응으로 올린 알림입니다.")
    }
)
async def add_risk_action(
    event_id: int,
    action: RiskEventActionCreateDTO,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    detail = await doctor_service.add_risk_action(current_doctor.id, event_id, action)

    return ApiResponseDTO(
        success=True,
        message="조치 기록 추가 완료",
        data=detail
    )


# ===== F-04 감정 그래프 팝업 (Figma: Doctor_detailmind) =====

# 15. 감정 리포트
@router.get(
    "/patients/{patient_id}/emotion-report",
    summary="감정 리포트 (요약·일별 기분·주별 감정 비율·키워드·시간대)",
    response_model=ApiResponseDTO[EmotionReportResponseDTO],
    responses={403: NOT_IN_CHARGE}
)
async def get_emotion_report(
    patient_id: int,
    period: Literal["week", "month", "3months"] = Query(default="week", description="week: 1주 / month: 1개월 / 3months: 3개월"),
    start: date | None = Query(default=None, alias="from", description="기간 첫날 (없으면 오늘로 끝나는 기간)"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    report = await doctor_service.get_emotion_report(current_doctor.id, patient_id, period, start)

    return ApiResponseDTO(
        success=True,
        message="감정 리포트 조회 완료",
        data=report
    )


# ===== F-03 설문조사 결과 팝업 (Figma: Doctor_detailsurvey) =====

# 16. 사전 문진 결과
@router.get(
    "/patients/{patient_id}/intake",
    summary="사전 문진 결과 (척도 점수·문항별 응답·주호소)",
    response_model=ApiResponseDTO[IntakeResultResponseDTO],
    responses={
        403: NOT_IN_CHARGE,
        404: error_example("문진 없음", "사전 문진 결과가 없습니다.")
    }
)
async def get_intake_result(
    patient_id: int,
    session_id: int | None = Query(default=None, alias="sessionId", description="문진 세션 id (없으면 가장 최근 문진)"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    result = await doctor_service.get_intake_result(current_doctor.id, patient_id, session_id)

    return ApiResponseDTO(
        success=True,
        message="사전 문진 결과 조회 완료",
        data=result
    )


# ===== F-07 예약 일정 팝업 (Figma: Doctor_DetailReservation) =====

NOT_MINE = error_example("의사가 아니거나 내 예약·담당 환자가 아님", "내 예약만 바꿀 수 있습니다.")
APPOINTMENT_NOT_FOUND = error_example("예약 없음", "예약이 존재하지 않습니다.")


# 17. 환자별 예약
@router.get(
    "/patients/{patient_id}/appointments",
    summary="환자별 예약 (월) + 변경·취소·노쇼 횟수",
    response_model=ApiResponseDTO[PatientAppointmentsResponseDTO],
    responses={403: NOT_IN_CHARGE}
)
async def get_patient_appointments(
    patient_id: int,
    month: str | None = Query(default=None, pattern=MONTH_PATTERN, description="YYYY-MM (없으면 이번 달)"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    appointments = await doctor_service.get_patient_appointments(current_doctor.id, patient_id, month)

    return ApiResponseDTO(
        success=True,
        message="환자 예약 조회 완료",
        data=appointments
    )


# 18. 예약 추가
@router.post(
    "/appointments",
    summary="예약 추가 (환자·의사 캘린더 일정도 함께 생성)",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[AppointmentDetailResponseDTO],
    responses={
        400: error_example("시간·진료실 오류", "지난 시각으로는 예약할 수 없습니다."),
        403: NOT_IN_CHARGE,
        404: error_example("의사 프로필 없음", "의사 프로필이 없습니다."),
        409: error_example("시간 겹침", "같은 시간에 다른 예약이 있습니다.")
    }
)
async def create_appointment(
    request: AppointmentCreateDTO,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    appointment = await doctor_service.create_appointment(current_doctor.id, request)

    return ApiResponseDTO(
        success=True,
        message="예약 추가 완료",
        data=appointment
    )


# 19. 일정 변경
@router.put(
    "/appointments/{appointment_id}",
    summary="예약 일정 변경 (변경 이력 기록, 캘린더 일정 이동)",
    response_model=ApiResponseDTO[AppointmentDetailResponseDTO],
    responses={
        400: error_example("시간 오류", "지난 시각으로는 예약할 수 없습니다."),
        403: NOT_MINE,
        404: APPOINTMENT_NOT_FOUND,
        409: error_example("겹침·바꿀 수 없는 상태", "같은 시간에 다른 예약이 있습니다.")
    }
)
async def reschedule_appointment(
    appointment_id: int,
    request: AppointmentRescheduleDTO,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    appointment = await doctor_service.reschedule_appointment(current_doctor.id, appointment_id, request)

    return ApiResponseDTO(
        success=True,
        message="일정 변경 완료",
        data=appointment
    )


# 20. 예약 취소
@router.post(
    "/appointments/{appointment_id}/cancel",
    summary="예약 취소 (변경 이력 기록, 캘린더 일정 삭제)",
    response_model=ApiResponseDTO[AppointmentDetailResponseDTO],
    responses={
        403: NOT_MINE,
        404: APPOINTMENT_NOT_FOUND,
        409: error_example("취소할 수 없는 상태", "예약됨·대기 중인 예약만 취소할 수 있습니다.")
    }
)
async def cancel_appointment(
    appointment_id: int,
    request: AppointmentCancelDTO,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    appointment = await doctor_service.cancel_appointment(current_doctor.id, appointment_id, request)

    return ApiResponseDTO(
        success=True,
        message="예약 취소 완료",
        data=appointment
    )


# 21. 진료 상태 변경
@router.put(
    "/appointments/{appointment_id}/status",
    summary="진료 상태 변경 (waiting·in_progress·completed·no_show)",
    response_model=ApiResponseDTO[AppointmentDetailResponseDTO],
    responses={
        403: NOT_MINE,
        404: APPOINTMENT_NOT_FOUND,
        409: error_example("바꿀 수 없는 상태", "지금 상태에서는 completed(으)로 바꿀 수 없습니다.")
    }
)
async def update_appointment_status(
    appointment_id: int,
    request: AppointmentStatusUpdateDTO,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    doctor_service: DoctorService = Depends(get_doctor_service)
):
    appointment = await doctor_service.update_appointment_status(current_doctor.id, appointment_id, request)

    return ApiResponseDTO(
        success=True,
        message="진료 상태 변경 완료",
        data=appointment
    )
