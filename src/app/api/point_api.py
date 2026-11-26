from typing import Literal
from fastapi import APIRouter, Depends, Query
from app.service.point_service import get_point_service, PointService
from app.schema.user_schema import UserClaimDTO
from app.schema.common_schema import ApiResponseDTO
from app.schema.point_schema import PointSummaryResponseDTO, PointHistoryListResponseDTO
from app.dependencie.auth_dependency import get_current_user

router = APIRouter()

# 내 포인트 요약(잔액, 오늘 모은 것, 이번 달 모은 것)
@router.get(
    "",
    summary="내 포인트 요약",
    response_model=ApiResponseDTO[PointSummaryResponseDTO]
)
async def get_point_summary(
    current_user: UserClaimDTO = Depends(get_current_user),
    service: PointService = Depends(get_point_service)
):
    data = await service.get_summary(current_user.id)
    return ApiResponseDTO(success=True, message="포인트 조회 완료", data=data)

#포인트 기록(전체&획득&사용 탭, 최신순, 더보기)
@router.get(
    "/histories",
    summary = "포인트 기록",
    response_model= ApiResponseDTO[PointHistoryListResponseDTO]
)
async def get_point_histories(
    tab: Literal["all", "earn", "spend"] = Query("all", alias="type", description="all 전체 · earn 획득 · spend 사용"),
    cursor: int | None = Query(None, description="다음 페이지: 직전 응답의 nextCursor"),
    size: int = Query(20, ge=1, le=50),
    current_user:UserClaimDTO = Depends(get_current_user),
    service: PointService = Depends(get_point_service)
):
    data = await service.get_histories(current_user.id,tab,cursor,size)
    return ApiResponseDTO(success=True,message="포인트 기록 조회 완료", data=data)
