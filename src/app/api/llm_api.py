from fastapi import APIRouter, Depends, Query, status
from app.service.llm_service import get_llm_service, LlmService
from app.schema.user_schema import UserClaimDTO
from app.schema.llm_schema import (
    ScheduledSessionCreateDTO,
    SendMessageRequestDTO,
    ChatSessionResponseDTO,
    MainSessionResponseDTO,
    MessageListResponseDTO,
    SendMessageResponseDTO,
)
from app.schema.common_schema import ApiResponseDTO
from app.dependencie.auth_dependency import get_current_user, get_current_doctor


# AI 상담(LLM) API
# - router: 환자용. main.py에서 prefix="/chat"으로 등록한다. (인증: get_current_user)
# - doctor_router: 의사용. main.py에서 prefix="/doctor"로 등록한다. (인증: get_current_doctor)
# - 사용자가 세션을 직접 종료하는 API는 없다. (프론트에 종료 버튼 없음)
router = APIRouter()
doctor_router = APIRouter()


# Swagger 문서용 공통 에러 응답
def error_example(description: str, detail: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"example": {"detail": detail}}}
    }

SESSION_NOT_FOUND = error_example("세션이 없거나 본인 세션이 아님", "세션이 존재하지 않습니다.")
NOT_STARTABLE = error_example("시작할 수 없는 상태이거나 이미 진행 중인 세션이 있음", "이미 진행 중인 세션이 있습니다.")
NOT_ACCESS_TIME = error_example("접속 시간이 아니거나 마감이 지남", "접속 가능 시간이 지났습니다.")
NOT_ACTIVE = error_example("진행 중인 세션이 아니거나 이미 처리 중인 메시지", "진행 중인 세션이 아닙니다.")
LLM_FAILED = error_example("LLM 답변 생성 실패 (재시도 포함)", "llm답변 오류!")
NOT_IN_CHARGE = error_example("의사가 아니거나 담당 환자가 아님", "담당 환자가 아닙니다.")
INVALID_CHECKLIST = error_example("체크리스트 항목 오류", "존재하지 않거나 사용할 수 없는 체크리스트 항목이 포함되어 있습니다.")
PERIOD_OVERLAP = error_example("기존 세션과 접속 기간이 겹침", "해당 환자의 다른 세션과 접속 기간이 겹칩니다.")


# ============================================================
# 환자용 (prefix="/chat")
# ============================================================

# 1. 상담 메인: 진행 중 세션, 없으면 가장 가까운 예정 세션 (없으면 data=null)
@router.get(
    "/sessions/main",
    summary="상담 메인 세션 조회",
    response_model=ApiResponseDTO[MainSessionResponseDTO | None]
)
async def get_main_session(
    current_user: UserClaimDTO = Depends(get_current_user),
    llm_service: LlmService = Depends(get_llm_service)
):
    session = await llm_service.get_main_session(current_user.id)

    return ApiResponseDTO(
        success=True,
        message="상담 메인 세션 조회 완료" if session else "예정된 상담 세션이 없습니다.",
        data=session
    )


# 2. 세션 시작 (SCHEDULED -> ACTIVE). 접속 시간(scheduled_at ~ expires_at)은 이때 한 번만 검증
@router.post(
    "/sessions/{session_id}/start",
    summary="상담 세션 시작",
    response_model=ApiResponseDTO[ChatSessionResponseDTO],
    responses={400: NOT_ACCESS_TIME, 404: SESSION_NOT_FOUND, 409: NOT_STARTABLE}
)
async def start_session(
    session_id: int,
    current_user: UserClaimDTO = Depends(get_current_user),
    llm_service: LlmService = Depends(get_llm_service)
):
    session = await llm_service.start_session(current_user.id, session_id)

    return ApiResponseDTO(
        success=True,
        message="상담 세션 시작",
        data=session
    )


# 3. 대화 기록 조회 (커서 방식: afterSeq 이후 limit개, nextCursor가 null이면 마지막 페이지)
# TODO: limit 기본값 확정 필요 (임시값 20)
@router.get(
    "/sessions/{session_id}/messages",
    summary="상담 대화 기록 조회",
    response_model=ApiResponseDTO[MessageListResponseDTO],
    responses={404: SESSION_NOT_FOUND}
)
async def get_messages(
    session_id: int,
    after_seq: int | None = Query(default=None, alias="afterSeq", ge=0, description="이 seq 이후부터 조회 (없으면 처음부터)"),
    limit: int = Query(default=20, ge=1, le=100, description="한 번에 가져올 개수"),
    current_user: UserClaimDTO = Depends(get_current_user),
    llm_service: LlmService = Depends(get_llm_service)
):
    messages = await llm_service.get_messages(current_user.id, session_id, after_seq, limit)

    return ApiResponseDTO(
        success=True,
        message="대화 기록 조회 완료",
        data=messages
    )


# 4. 메시지 전송 (한 턴 처리: 사용자 메시지 저장 -> LLM 답변 -> 체크리스트 반영 -> 종료 판정)
# - 같은 clientMessageId로 재전송하면 이미 만든 답변을 돌려준다.
# - LLM이 재시도 후에도 실패하면 502 (detail: "llm답변 오류!"). 이 문구는 저장되지 않는다.
# TODO: 응답 코드 확정 필요 (임시 200)
@router.post(
    "/sessions/{session_id}/messages",
    summary="상담 메시지 전송",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponseDTO[SendMessageResponseDTO],
    responses={404: SESSION_NOT_FOUND, 409: NOT_ACTIVE, 502: LLM_FAILED}
)
async def send_message(
    session_id: int,
    request: SendMessageRequestDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    llm_service: LlmService = Depends(get_llm_service)
):
    result = await llm_service.send_message(
        current_user.id,
        session_id,
        request.client_message_id,
        request.content,
        request.input_type,
    )

    return ApiResponseDTO(
        success=True,
        message="메시지 전송 완료",
        data=result
    )


# ============================================================
# 의사용 (prefix="/doctor")
# ============================================================

# 5. 예정 세션 생성 (한 번 호출에 세션 1건)
# - 담당 환자 확인, 기존 세션과 접속 기간 중복 확인, 체크리스트 항목 검증
@doctor_router.post(
    "/chat-sessions",
    summary="예정 상담 세션 생성",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[ChatSessionResponseDTO],
    responses={400: INVALID_CHECKLIST, 403: NOT_IN_CHARGE, 409: PERIOD_OVERLAP}
)
async def create_scheduled_session(
    request: ScheduledSessionCreateDTO,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    llm_service: LlmService = Depends(get_llm_service)
):
    session = await llm_service.create_scheduled_session(current_doctor.id, request)

    return ApiResponseDTO(
        success=True,
        message="예정 상담 세션 생성 완료",
        data=session
    )
