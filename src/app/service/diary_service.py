import math
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from fastapi import Depends, HTTPException, status
from app.repository.diary_repository import DiaryRepository, get_diary_repository
from app.model.diary_model import Diary
from app.schema.common_schema import PageRequestDTO, PageResponseDTO
from app.schema.diary_schema import DiaryCreateDTO, DiaryUpdateDTO, DiaryResponseDTO

KST = timezone(timedelta(hours=9)) # UTC+9


# 마음 일기 비즈니스 로직, 예외 처리, 트랜잭션 관리
class DiaryService:

    def __init__(self, repo: DiaryRepository):
        self.repo = repo


    # 날짜 -> 한국 시간 자정 (diary_date는 DateTime 컬럼이라 날짜를 자정으로 저장한다.)
    @staticmethod
    def _to_kst_start(day: date) -> datetime:
        return datetime(day.year, day.month, day.day, tzinfo=KST)


    # ORM -> 응답 DTO (날짜는 한국 시간 기준으로 변환)
    @staticmethod
    def _to_response(diary: Diary) -> DiaryResponseDTO:
        return DiaryResponseDTO(
            diary_id=diary.diary_id,
            diary_date=diary.diary_date.astimezone(KST).date(),
            content=diary.content,
            created_at=diary.created_at,
            updated_at=diary.updated_at
        )


    # 일기 작성
    async def create_diary(self, user_id: int, dto: DiaryCreateDTO) -> DiaryResponseDTO:
        today = datetime.now(KST).date()
        diary_date = dto.diary_date or today

        # 미래 날짜 일기는 쓸 수 없다.
        if diary_date > today:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="미래 날짜의 일기는 작성할 수 없습니다."
            )

        diary = await self.repo.create_diary(user_id, self._to_kst_start(diary_date), dto.content)
        return self._to_response(diary)


    # 일기 목록 (month: "YYYY-MM"이면 해당 월만)
    async def get_diaries(
        self, user_id: int, page: PageRequestDTO, month: str | None = None
    ) -> PageResponseDTO[DiaryResponseDTO]:
        start = end = None
        if month:
            try:
                year, mon = (int(x) for x in month.split("-"))
                first = date(year, mon, 1)
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="month는 YYYY-MM 형식이어야 합니다."
                )
            start = self._to_kst_start(first)
            end = self._to_kst_start(first + timedelta(days=monthrange(year, mon)[1]))

        diaries, total = await self.repo.find_diaries(user_id, page.offset, page.limit, start, end)

        return PageResponseDTO(
            total_count=total,
            total_pages=math.ceil(total / page.limit),
            offset=page.offset,
            limit=page.limit,
            items=[self._to_response(d) for d in diaries]
        )


    # 일기 상세
    async def get_diary(self, user_id: int, diary_id: int) -> DiaryResponseDTO:
        diary = await self.repo.find_diary(user_id, diary_id)
        if not diary:
            raise self._not_found()
        return self._to_response(diary)


    # 일기 수정 (보낸 값만 수정)
    async def update_diary(self, user_id: int, diary_id: int, dto: DiaryUpdateDTO) -> DiaryResponseDTO:
        update_data = dto.model_dump(exclude_unset=True, exclude_none=True)

        if "diary_date" in update_data:
            if update_data["diary_date"] > datetime.now(KST).date():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="미래 날짜의 일기는 작성할 수 없습니다."
                )
            update_data["diary_date"] = self._to_kst_start(update_data["diary_date"])

        diary = await self.repo.update_diary(user_id, diary_id, update_data)
        if not diary:
            raise self._not_found()
        return self._to_response(diary)


    # 일기 삭제
    async def delete_diary(self, user_id: int, diary_id: int) -> None:
        if not await self.repo.delete_diary(user_id, diary_id, datetime.now(KST)):
            raise self._not_found()


    # 없거나 남의 일기이거나 삭제된 일기는 모두 404 (존재 여부를 노출하지 않는다.)
    @staticmethod
    def _not_found() -> HTTPException:
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="일기가 존재하지 않습니다."
        )



def get_diary_service(repo: DiaryRepository = Depends(get_diary_repository)) -> DiaryService:
    return DiaryService(repo)
