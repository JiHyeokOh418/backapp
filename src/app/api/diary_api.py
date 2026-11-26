from fastapi import APIRouter, Depends, Query, status
from app.service.diary_service import get_diary_service, DiaryService
from app.schema.user_schema import UserClaimDTO
from app.schema.common_schema import ApiResponseDTO, PageRequestDTO, PageResponseDTO
from app.schema.diary_schema import DiaryCreateDTO, DiaryUpdateDTO, DiaryResponseDTO
from app.dependencie.auth_dependency import get_current_user


router = APIRouter()


# 일기 쓰기
@router.post(
    "",
    summary="마음 일기 작성",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponseDTO[DiaryResponseDTO]
)
async def create_diary(
    dto: DiaryCreateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DiaryService = Depends(get_diary_service)
):
    data = await service.create_diary(current_user.id, dto)
    return ApiResponseDTO(success=True, message="일기 작성 완료", data=data)


# 일기 목록 (최신 날짜순)
@router.get(
    "",
    summary="마음 일기 목록",
    response_model=ApiResponseDTO[PageResponseDTO[DiaryResponseDTO]]
)
async def get_diaries(
    month: str | None = Query(default=None, description="YYYY-MM 형식, 없으면 전체"),
    page: PageRequestDTO = Depends(),
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DiaryService = Depends(get_diary_service)
):
    data = await service.get_diaries(current_user.id, page, month)
    return ApiResponseDTO(success=True, message="일기 목록 조회 완료", data=data)


# 일기 상세
@router.get(
    "/{diary_id}",
    summary="마음 일기 상세",
    response_model=ApiResponseDTO[DiaryResponseDTO]
)
async def get_diary(
    diary_id: int,
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DiaryService = Depends(get_diary_service)
):
    data = await service.get_diary(current_user.id, diary_id)
    return ApiResponseDTO(success=True, message="일기 조회 완료", data=data)


# 일기 수정 (보낸 값만 수정)
@router.patch(
    "/{diary_id}",
    summary="마음 일기 수정",
    response_model=ApiResponseDTO[DiaryResponseDTO]
)
async def update_diary(
    diary_id: int,
    dto: DiaryUpdateDTO,
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DiaryService = Depends(get_diary_service)
):
    data = await service.update_diary(current_user.id, diary_id, dto)
    return ApiResponseDTO(success=True, message="일기 수정 완료", data=data)


# 일기 삭제
@router.delete(
    "/{diary_id}",
    summary="마음 일기 삭제",
    response_model=ApiResponseDTO
)
async def delete_diary(
    diary_id: int,
    current_user: UserClaimDTO = Depends(get_current_user),
    service: DiaryService = Depends(get_diary_service)
):
    await service.delete_diary(current_user.id, diary_id)
    return ApiResponseDTO(success=True, message="일기 삭제 완료")
