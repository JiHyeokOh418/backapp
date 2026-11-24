from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db


# 캘린더 DB 접근
class CalendarRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db

    # TODO: 조회/저장 쿼리 추가


def get_calendar_repository(db: AsyncSession = Depends(get_postgresql_db)) -> CalendarRepository:
    return CalendarRepository(db)
