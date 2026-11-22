from fastapi import APIRouter, Depends, Query, status
from app.service.doctor_verification_service import (
    get_doctor_verification_service, DoctorVerificationService
)
from app.enum.user_enum import VerificationStatus
from app.schema.user_schema import UserClaimDTO
from app.schema.doctor_verification_schema import (
    HospitalResponseDTO,
    DoctorVerificationCreateDTO,
    DoctorVerificationRejectDTO,
    DoctorVerificationResponseDTO,
    MyVerificationResponseDTO,
)
from app.schema.common_schema import ApiResponseDTO
from app.dependencie.auth_dependency import get_current_user


# 의사 회원가입(승인 신청) - D-03, D-04
# - 승인 전에는 role이 patient라 get_current_doctor가 아닌 get_current_user로 받는다.
# - main.py에서 prefix="/doctor"로 등록한다.
router = APIRouter()

# 관리자 승인·반려 - main.py에서 prefix="/admin"으로 등록한다.
admin_router = APIRouter()


# Swagger 문서용 공통 에러 응답
def error_example(description: str, detail: str) -> dict:
    return {
        "description": description,
        "content": {"application/json": {"example": {"detail": detail}}}
    }

NOT_ADMIN = error_example("관리자가 아님", "관리자만 사용할 수 있습니다.")
NOT_FOUND = error_example("신청이 없음", "신청이 존재하지 않습니다.")
ALREADY_REVIEWED = error_example("이미 승인·반려된 신청", "이미 처리된 신청입니다.")


# 병원 검색 (D-03 소속 병원 선택)
@router.get(
    "/hospitals",
    summary="병원 검색",
    response_model=ApiResponseDTO[list[HospitalResponseDTO]]
)
async def search_hospitals(
    q: str = Query(min_length=1, max_length=100, description="병원 이름 검색어"),
    limit: int = Query(default=20, ge=1, le=50),
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DoctorVerificationService = Depends(get_doctor_verification_service)
):
    hospitals = await service.search_hospitals(q, limit)

    return ApiResponseDTO(
        success=True,
        message="병원 검색 완료",
        data=hospitals
    )


# 의사 승인 신청 (D-03)
@router.post(
    "/verifications",
    summary="의사 승인 신청",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[DoctorVerificationResponseDTO],
    responses={
        404: error_example("병원이 없음", "병원이 존재하지 않습니다."),
        409: error_example("이미 의사이거나 대기 중인 신청이 있음", "승인 대기 중인 신청이 이미 있습니다.")
    }
)
async def apply(
    verification: DoctorVerificationCreateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DoctorVerificationService = Depends(get_doctor_verification_service)
):
    created = await service.apply(current_user, verification)

    return ApiResponseDTO(
        success=True,
        message="의사 승인 신청 완료",
        data=created
    )


# 내 신청 상태 (D-04)
# - verification이 null이면 신청 전 -> D-03
# - reloginRequired가 true면 승인됨 -> 로그아웃 후 다시 로그인하도록 안내
@router.get(
    "/verifications/me",
    summary="내 의사 승인 신청 상태",
    response_model=ApiResponseDTO[MyVerificationResponseDTO]
)
async def get_my_verification(
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DoctorVerificationService = Depends(get_doctor_verification_service)
):
    my_verification = await service.get_my_verification(current_user)

    return ApiResponseDTO(
        success=True,
        message="신청 상태 조회 완료",
        data=my_verification
    )


# 신청 목록 (관리자)
@admin_router.get(
    "/doctor-verifications",
    summary="의사 승인 신청 목록",
    response_model=ApiResponseDTO[list[DoctorVerificationResponseDTO]],
    responses={403: NOT_ADMIN}
)
async def get_verifications(
    verification_status: VerificationStatus | None = Query(
        default=VerificationStatus.PENDING, alias="status", description="없으면 pending"
    ),
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DoctorVerificationService = Depends(get_doctor_verification_service)
):
    verifications = await service.get_verifications(current_user.id, verification_status)

    return ApiResponseDTO(
        success=True,
        message="신청 목록 조회 완료",
        data=verifications
    )


# 승인 (관리자) -> 신청자 role=doctor, doctor_profiles 생성
# - 신청자는 다시 로그인해야 의사 기능을 쓸 수 있다.
@admin_router.post(
    "/doctor-verifications/{verification_id}/approve",
    summary="의사 승인",
    response_model=ApiResponseDTO[DoctorVerificationResponseDTO],
    responses={403: NOT_ADMIN, 404: NOT_FOUND, 409: ALREADY_REVIEWED}
)
async def approve(
    verification_id: int,
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DoctorVerificationService = Depends(get_doctor_verification_service)
):
    approved = await service.approve(current_user.id, verification_id)

    return ApiResponseDTO(
        success=True,
        message="의사 승인 완료 (신청자는 다시 로그인해야 합니다)",
        data=approved
    )


# 반려 (관리자)
@admin_router.post(
    "/doctor-verifications/{verification_id}/reject",
    summary="의사 승인 반려",
    response_model=ApiResponseDTO[DoctorVerificationResponseDTO],
    responses={403: NOT_ADMIN, 404: NOT_FOUND, 409: ALREADY_REVIEWED}
)
async def reject(
    verification_id: int,
    body: DoctorVerificationRejectDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DoctorVerificationService = Depends(get_doctor_verification_service)
):
    rejected = await service.reject(current_user.id, verification_id, body.reject_reason)

    return ApiResponseDTO(
        success=True,
        message="의사 승인 반려 완료",
        data=rejected
    )
