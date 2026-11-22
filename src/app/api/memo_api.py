from typing import Literal
from fastapi import APIRouter, Depends, Query, status
from app.service.memo_service import get_memo_service, MemoService
from app.schema.user_schema import UserClaimDTO
from app.schema.memo_schema import (
    MemoCreateDTO,
    MemoUpdateDTO,
    MemoResponseDTO,
    MemoListResponseDTO,
)
from app.schema.common_schema import ApiResponseDTO
from app.dependencie.auth_dependency import get_current_doctor


# 의사 메모 서브페이지 (Doctor_DetailMemo 팝업)
# - main.py에서 prefix="/doctor"로 등록한다.
router = APIRouter()


# Swagger 문서용 공통 에러 응답
def error_example(description: str, detail: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"example": {"detail": detail}}}
    }

NOT_IN_CHARGE = error_example("의사가 아니거나 담당 환자가 아님", "담당 환자가 아닙니다.")
NOT_WRITER = error_example("의사가 아니거나 작성자가 아님", "작성자만 수정·삭제할 수 있습니다.")
MEMO_NOT_FOUND = error_example("메모가 없거나 삭제됨", "메모가 존재하지 않습니다.")


# 메모 목록
# - 고정 메모가 항상 위, 그 다음 sort 기준
# - totalCount, pinnedCount는 pinned 필터와 상관없이 전체 기준 (헤더·탭 숫자용)
@router.get(
    "/patients/{patient_id}/memos",
    summary="환자 메모 목록",
    response_model=ApiResponseDTO[MemoListResponseDTO],
    responses={403: NOT_IN_CHARGE}
)
async def get_memos(
    patient_id: int,
    pinned: bool | None = Query(default=None, description="true: 고정 탭 / 없으면 전체 탭"),
    sort: Literal["latest", "oldest"] = Query(default="latest", description="latest: 최신순 / oldest: 오래된순"),
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    memo_service: MemoService = Depends(get_memo_service)
):
    memos = await memo_service.get_memos(current_doctor.id, patient_id, pinned, sort)

    return ApiResponseDTO(
        success=True,
        message="메모 목록 조회 완료",
        data=memos
    )


# 메모 작성
@router.post(
    "/patients/{patient_id}/memos",
    summary="환자 메모 작성",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[MemoResponseDTO],
    responses={403: NOT_IN_CHARGE}
)
async def create_memo(
    patient_id: int,
    memo: MemoCreateDTO,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    memo_service: MemoService = Depends(get_memo_service)
):
    created_memo = await memo_service.create_memo(current_doctor.id, patient_id, memo)

    return ApiResponseDTO(
        success=True,
        message="메모 작성 완료",
        data=created_memo
    )


# 메모 수정·고정 (보낸 값만 수정)
# - 내용·분류를 바꾸면 "수정됨"(isEdited=true), 고정만 바꾸면 그대로
@router.put(
    "/memos/{memo_id}",
    summary="메모 수정·고정",
    response_model=ApiResponseDTO[MemoResponseDTO],
    responses={403: NOT_WRITER, 404: MEMO_NOT_FOUND}
)
async def update_memo(
    memo_id: int,
    memo: MemoUpdateDTO,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    memo_service: MemoService = Depends(get_memo_service)
):
    updated_memo = await memo_service.update_memo(current_doctor.id, memo_id, memo)

    return ApiResponseDTO(
        success=True,
        message="메모 수정 완료",
        data=updated_memo
    )


# 메모 삭제 (soft delete)
@router.delete(
    "/memos/{memo_id}",
    summary="메모 삭제",
    response_model=ApiResponseDTO,
    responses={403: NOT_WRITER, 404: MEMO_NOT_FOUND}
)
async def delete_memo(
    memo_id: int,
    current_doctor: UserClaimDTO = Depends(get_current_doctor),
    memo_service: MemoService = Depends(get_memo_service)
):
    await memo_service.delete_memo(current_doctor.id, memo_id)

    return ApiResponseDTO(
        success=True,
        message="메모 삭제 완료"
    )
