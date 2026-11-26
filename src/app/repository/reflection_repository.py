from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db


# 마음 돌아보기 (주간/월간 감정 분석 집계) DB 접근
class ReflectionRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db

    # TODO: 조회/저장 쿼리 추가


def get_reflection_repository(db: AsyncSession = Depends(get_postgresql_db)) -> ReflectionRepository:
    return ReflectionRepository(db)
