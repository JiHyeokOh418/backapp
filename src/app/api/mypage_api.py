from fastapi import APIRouter, Depends
from app.service.mypage_service import get_mypage_service, MypageService
from app.schema.user_schema import UserClaimDTO
from app.schema.common_schema import ApiResponseDTO
from app.schema.mypage_schema import (
    MypageSummaryResponseDTO,
    MyProfileResponseDTO,
    MyProfileUpdateDTO,
    UserSettingResponseDTO,
    UserSettingUpdateDTO,
)
from app.dependencie.auth_dependency import get_current_user


router = APIRouter()


# 마이페이지 메인 (프로필 카드 + 설정)
@router.get(
    "",
    summary="마이페이지 메인 요약",
    response_model=ApiResponseDTO[MypageSummaryResponseDTO]
)
async def get_mypage(
    current_user: UserClaimDTO = Depends(get_current_user),
    service: MypageService = Depends(get_mypage_service)
):
    data = await service.get_summary(current_user.id)
    return ApiResponseDTO(success=True, message="마이페이지 조회 완료", data=data)


# 내 정보 (기본 정보, 연결된 진료, 공유 설정)
@router.get(
    "/profile",
    summary="내 정보 조회",
    response_model=ApiResponseDTO[MyProfileResponseDTO]
)
async def get_profile(
    current_user: UserClaimDTO = Depends(get_current_user),
    service: MypageService = Depends(get_mypage_service)
):
    data = await service.get_profile(current_user.id)
    return ApiResponseDTO(success=True, message="내 정보 조회 완료", data=data)


# 내 정보 수정 (보낸 값만 수정)
@router.patch(
    "/profile",
    summary="내 정보 수정",
    response_model=ApiResponseDTO[MyProfileResponseDTO]
)
async def update_profile(
    dto: MyProfileUpdateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    service: MypageService = Depends(get_mypage_service)
):
    data = await service.update_profile(current_user.id, dto)
    return ApiResponseDTO(success=True, message="내 정보 수정 완료", data=data)


# 설정 조회
@router.get(
    "/settings",
    summary="설정 조회",
    response_model=ApiResponseDTO[UserSettingResponseDTO]
)
async def get_settings(
    current_user: UserClaimDTO = Depends(get_current_user),
    service: MypageService = Depends(get_mypage_service)
):
    data = await service.get_setting(current_user.id)
    return ApiResponseDTO(success=True, message="설정 조회 완료", data=data)


# 설정 수정 (숫자·기록 현황 숨기기, 의사 공유)
@router.patch(
    "/settings",
    summary="설정 수정",
    response_model=ApiResponseDTO[UserSettingResponseDTO]
)
async def update_settings(
    dto: UserSettingUpdateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    service: MypageService = Depends(get_mypage_service)
):
    data = await service.update_setting(current_user.id, dto)
    return ApiResponseDTO(success=True, message="설정 수정 완료", data=data)
