from fastapi import APIRouter, Depends, Query, status
from app.service.care_request_service import get_care_request_service, CareRequestService
from app.schema.user_schema import UserClaimDTO
from app.schema.care_request_schema import (
    CareRequestCreateDTO,
    CareRequestResponseDTO,
    HospitalCareRequestDTO,
    HospitalCareRequestTab,
    CareRequestRespondDTO,
    RequestMessageCreateDTO,
    RequestMessageDTO,
    CareRequestAppointmentCreateDTO,
    CareRelationRegisterDTO,
    CareRelationResponseDTO,
    CareRequestDirectCreateDTO,
)
from app.schema.doctor_schema import AppointmentDetailResponseDTO
from app.schema.common_schema import ApiResponseDTO
from app.enums.care_request_enum import CareRequestStatus
from app.dependencie.auth_dependency import get_current_user, get_current_doctor


# 진료 연결 API (연결-01 ~ 연결-10)
# - router: 환자용(+ 채팅은 환자·의사 공용). main.py에서 prefix="/care-requests"로 등록한다. (인증: get_current_user)
# - doctor_router: 병원 측. main.py에서 prefix="/doctor"로 등록하고, 경로는 "/care-requests/..."로 둔다. (인증: get_current_doctor)
router = APIRouter()
doctor_router = APIRouter()


# Swagger 문서용 공통 에러 응답
def error_example(description: str, detail: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"example": {"detail": detail}}}
    }

NOT_PATIENT = error_example("환자가 아님", "환자만 사용할 수 있습니다.")
NOT_DOCTOR = error_example("의사가 아님", "get_current_doctor 의사만 사용할 수 있습니다.")
REQUEST_NOT_FOUND = error_example("요청이 없거나 본인 요청이 아님", "진료 요청이 존재하지 않습니다.")
NO_DOCTOR_PROFILE = error_example("의사 프로필 없음", "의사 프로필이 없습니다.")
NOT_CHAT_MEMBER = error_example("요청한 환자나 연결된 병원 의사가 아님", "채팅 참여자가 아닙니다.")
REQUEST_NOT_EXISTS = error_example("요청 없음", "진료 요청이 존재하지 않습니다.")

# 요청 결과 상태별 안내 문구 (위기 상태여도 위험도 문구는 쓰지 않는다, 공통-05)
CREATE_MESSAGES = {
    CareRequestStatus.CONTACTING: "주변 병원에 연락했어요.",
    CareRequestStatus.EXPIRED: "주변에 연락 가능한 병원이 없어요.",
    CareRequestStatus.CRISIS: "진료 요청을 접수했어요.",
}


# ============================================================
# 환자용 (prefix="/care-requests")
# ============================================================

# 1. 진료 요청 (연결-01·02): 반경 안 가까운 병원 최대 3곳에 연락
# - status: contacting(병원 응답 대기) / expired(주변 병원 없음) / crisis(위기 안내 화면)
@router.post(
    "",
    summary="진료 요청",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[CareRequestResponseDTO],
    responses={
        403: NOT_PATIENT,
        409: error_example("진행 중인 요청이 있음", "진행 중인 진료 요청이 있습니다."),
    }
)
async def create_care_request(
    dto: CareRequestCreateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    care_request_service: CareRequestService = Depends(get_care_request_service)
):
    request = await care_request_service.create_request(current_user, dto)

    return ApiResponseDTO(
        success=True,
        message=CREATE_MESSAGES.get(request.status, "진료 요청 완료"),
        data=request
    )


# 2. 내 진행 중 요청 (requested·contacting·connected), 없으면 data=null
@router.get(
    "/me",
    summary="내 진행 중 진료 요청 조회",
    response_model=ApiResponseDTO[CareRequestResponseDTO | None],
    responses={403: NOT_PATIENT}
)
async def get_my_care_request(
    current_user: UserClaimDTO = Depends(get_current_user),
    care_request_service: CareRequestService = Depends(get_care_request_service)
):
    request = await care_request_service.get_my_active_request(current_user)

    return ApiResponseDTO(
        success=True,
        message="진행 중인 진료 요청 조회 완료" if request else "진행 중인 진료 요청이 없습니다.",
        data=request
    )


# 3. 요청 취소: requested·contacting·connected일 때만
@router.post(
    "/{request_id}/cancel",
    summary="진료 요청 취소",
    response_model=ApiResponseDTO[CareRequestResponseDTO],
    responses={
        403: NOT_PATIENT,
        404: REQUEST_NOT_FOUND,
        409: error_example("취소할 수 없는 상태", "취소할 수 없는 상태의 요청입니다."),
    }
)
async def cancel_care_request(
    request_id: int,
    current_user: UserClaimDTO = Depends(get_current_user),
    care_request_service: CareRequestService = Depends(get_care_request_service)
):
    request = await care_request_service.cancel_request(current_user, request_id)

    return ApiResponseDTO(
        success=True,
        message="진료 요청 취소 완료",
        data=request
    )


# 8. 빠른 진료 예약 (연결-10): 지금 담당 의사에게 직접 요청
# - 주변 병원 연락 없이 담당 의사 병원에 연락 1건. 이후 응답·채팅·예약 확정은 주변 병원 요청과 같다.
@router.post(
    "/direct",
    summary="담당 의사에게 빠른 진료 요청",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[CareRequestResponseDTO],
    responses={
        403: NOT_PATIENT,
        409: error_example("진행 중인 요청이 있음 / 담당 의사 없음", "담당 의사가 없습니다."),
    }
)
async def create_direct_care_request(
    dto: CareRequestDirectCreateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    care_request_service: CareRequestService = Depends(get_care_request_service)
):
    request = await care_request_service.create_direct_request(current_user, dto)

    return ApiResponseDTO(
        success=True,
        message="담당 의사에게 요청했어요." if request.status == CareRequestStatus.CONTACTING
        else CREATE_MESSAGES.get(request.status, "진료 요청 완료"),
        data=request
    )


# 9. 진료 후 담당 등록 (연결-09): register = 이 의사를 담당으로 / once = 이번만 (data=null)
@router.post(
    "/appointments/{appointment_id}/register",
    summary="진료 후 담당 의사 등록 선택",
    response_model=ApiResponseDTO[CareRelationResponseDTO | None],
    responses={
        403: NOT_PATIENT,
        404: error_example("예약이 없거나 내 예약이 아님", "예약이 존재하지 않습니다."),
        409: error_example("진료를 마치지 않은 예약", "진료를 마친 예약만 선택할 수 있습니다."),
    }
)
async def register_after_visit(
    appointment_id: int,
    dto: CareRelationRegisterDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    care_request_service: CareRequestService = Depends(get_care_request_service)
):
    relation = await care_request_service.register_after_visit(current_user, appointment_id, dto)

    return ApiResponseDTO(
        success=True,
        message="담당 의사로 등록했어요." if relation else "이번 진료만 이용했어요.",
        data=relation
    )


# ============================================================
# 예약 채팅 (환자·의사 공용, prefix="/care-requests", 연결-05)
# - 참여자: 요청한 환자 + 연결된 병원 소속 의사
# - 실시간 전송 없음: 프론트는 마지막으로 받은 messageId를 afterId로 넣어 폴링한다. (임의 결정 D-58)
# ============================================================

# 6. 메시지 목록 (오래된 순): 상대가 보낸 안 읽은 메시지는 읽음 처리
@router.get(
    "/{request_id}/messages",
    summary="예약 채팅 메시지 목록",
    response_model=ApiResponseDTO[list[RequestMessageDTO]],
    responses={403: NOT_CHAT_MEMBER, 404: REQUEST_NOT_EXISTS}
)
async def get_request_messages(
    request_id: int,
    after_id: int | None = Query(default=None, alias="afterId", ge=0, description="이 messageId 뒤 메시지만"),
    current_user: UserClaimDTO = Depends(get_current_user),
    care_request_service: CareRequestService = Depends(get_care_request_service)
):
    messages = await care_request_service.get_messages(current_user, request_id, after_id)

    return ApiResponseDTO(
        success=True,
        message="메시지 목록 조회 완료",
        data=messages
    )


# 7. 메시지 보내기: connected, 또는 booked이고 예약 진료일(KST)이 끝나기 전까지 (결정-47)
@router.post(
    "/{request_id}/messages",
    summary="예약 채팅 메시지 보내기",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[RequestMessageDTO],
    responses={
        403: NOT_CHAT_MEMBER,
        404: REQUEST_NOT_EXISTS,
        409: error_example("연결 전·취소·만료 또는 예약 진료일이 지남", "메시지를 보낼 수 없는 상태의 요청입니다."),
    }
)
async def send_request_message(
    request_id: int,
    dto: RequestMessageCreateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    care_request_service: CareRequestService = Depends(get_care_request_service)
):
    message = await care_request_service.send_message(current_user, request_id, dto)

    return ApiResponseDTO(
        success=True,
        message="메시지 전송 완료",
        data=message
    )


# ============================================================
# 병원 측 (prefix="/doctor", 경로 "/care-requests/...")
# ============================================================

# 4. 요청 목록 (화면-30): 내 병원(doctor_profiles.hospital_id)에 온 연락 기준
# - pending: 응답 기다리는 중 (기한 가까운 순) / connected: 우리 병원과 연결됨 / closed: 그 밖, 최근 30일
# - 환자 이름은 우리 병원과 연결된 뒤에만 내려준다. (그 전에는 patient=null)
@doctor_router.get(
    "/care-requests",
    summary="병원 측 진료 요청 목록",
    response_model=ApiResponseDTO[list[HospitalCareRequestDTO]],
    responses={403: NOT_DOCTOR, 404: NO_DOCTOR_PROFILE}
)
async def get_hospital_care_requests(
    tab: HospitalCareRequestTab = Query(default="pending", description="pending·connected·closed"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    care_request_service: CareRequestService = Depends(get_care_request_service)
):
    requests = await care_request_service.get_hospital_requests(current_doctor.id, tab)

    return ApiResponseDTO(
        success=True,
        message="진료 요청 목록 조회 완료",
        data=requests
    )


# 5. 가능·불가 응답 (연결-03·04)
# - available: 먼저 누른 병원 1곳만 연결된다. 늦은 병원은 409 "이미 연결된 요청입니다."
# - declined: 남은 병원이 없으면 요청이 바로 만료된다.
@doctor_router.post(
    "/care-requests/{request_id}/respond",
    summary="진료 요청 가능·불가 응답",
    response_model=ApiResponseDTO[HospitalCareRequestDTO],
    responses={
        403: NOT_DOCTOR,
        404: error_example("우리 병원에 온 요청이 아님 / 의사 프로필 없음", "진료 요청이 존재하지 않습니다."),
        409: error_example(
            "이미 응답·응답 시간 지남 / 다른 병원과 이미 연결 / 환자가 취소",
            "이미 응답했거나 응답 시간이 지난 요청입니다."
        ),
    }
)
async def respond_care_request(
    request_id: int,
    dto: CareRequestRespondDTO,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    care_request_service: CareRequestService = Depends(get_care_request_service)
):
    request = await care_request_service.respond(current_doctor.id, request_id, dto)

    return ApiResponseDTO(
        success=True,
        message="연결되었어요. 채팅으로 예약을 잡아 주세요." if dto.response == "available" else "불가로 응답했어요.",
        data=request
    )


# 10. 예약 확정 (연결-06·07, 화면-27): 예약 1건 + 환자·의사 일정 2건 + 요청 booked + 환자 알림
# - 응답은 F-07 예약 추가와 같은 DTO. 예약 변경·취소·진료 완료는 기존 /doctor/appointments API를 쓴다.
@doctor_router.post(
    "/care-requests/{request_id}/appointment",
    summary="진료 요청 예약 확정",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[AppointmentDetailResponseDTO],
    responses={
        400: error_example("시간·진료실 오류", "지난 시각으로는 예약할 수 없습니다."),
        403: error_example("연결된 병원 의사가 아님", "연결된 병원의 의사만 예약할 수 있습니다."),
        404: REQUEST_NOT_EXISTS,
        409: error_example("connected가 아님 / 시간 겹침", "예약을 확정할 수 없는 상태의 요청입니다."),
    }
)
async def create_care_request_appointment(
    request_id: int,
    dto: CareRequestAppointmentCreateDTO,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    care_request_service: CareRequestService = Depends(get_care_request_service)
):
    appointment = await care_request_service.create_appointment(current_doctor.id, request_id, dto)

    return ApiResponseDTO(
        success=True,
        message="예약 확정 완료",
        data=appointment
    )
