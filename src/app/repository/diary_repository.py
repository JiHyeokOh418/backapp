from datetime import datetime
from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db

# 모델, ORM
from app.models.diary_model import Diary


# 마음 일기 DB 접근 (조회/저장만 담당, 비즈니스 규칙은 service에서 처리)
class DiaryRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db


    # 1. 일기 작성
    async def create_diary(self, user_id: int, diary_date: datetime, content: str) -> Diary:
        diary = Diary(user_id=user_id, diary_date=diary_date, content=content)
        self.db.add(diary)
        await self.db.commit()
        await self.db.refresh(diary)
        return diary


    # 2. 일기 목록 - 삭제한 일기 제외, 기간(start 이상 end 미만) 선택
    async def find_diaries(
        self, user_id: int, offset: int, limit: int,
        start: datetime | None = None, end: datetime | None = None
    ) -> tuple[list[Diary], int]:
        conditions = [Diary.user_id == user_id, Diary.deleted_at.is_(None)]
        if start is not None:
            conditions.append(Diary.diary_date >= start)
        if end is not None:
            conditions.append(Diary.diary_date < end)

        total = await self.db.scalar(select(func.count()).select_from(Diary).where(*conditions))
        query = (
            select(Diary)
            .where(*conditions)
            .order_by(Diary.diary_date.desc(), Diary.diary_id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        return list(result.scalars().all()), total or 0


    # 3. 일기 단건 조회 - 내 일기만, 삭제한 일기 제외
    async def find_diary(self, user_id: int, diary_id: int) -> Diary | None:
        query = select(Diary).where(
            Diary.diary_id == diary_id,
            Diary.user_id == user_id,
            Diary.deleted_at.is_(None)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 4. 일기 수정
    async def update_diary(self, user_id: int, diary_id: int, update_data: dict) -> Diary | None:
        if not update_data:
            return await self.find_diary(user_id, diary_id)

        query = (
            update(Diary)
            .where(Diary.diary_id == diary_id, Diary.user_id == user_id, Diary.deleted_at.is_(None))
            .values(**update_data)
            .returning(Diary)
        )
        result = await self.db.execute(query)
        updated = result.scalar_one_or_none()
        await self.db.commit()
        return updated


    # 5. 일기 삭제 (soft delete: 분석 결과 등 연관 데이터 보존)
    async def delete_diary(self, user_id: int, diary_id: int, deleted_at: datetime) -> bool:
        query = (
            update(Diary)
            .where(Diary.diary_id == diary_id, Diary.user_id == user_id, Diary.deleted_at.is_(None))
            .values(deleted_at=deleted_at)
        )
        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0



def get_diary_repository(db: AsyncSession = Depends(get_postgresql_db)) -> DiaryRepository:
    return DiaryRepository(db)
