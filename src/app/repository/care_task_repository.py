from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db


# 오늘의 작은 돌봄 / 나만의 돌봄 (미션과 같은 개념으로 묶어서 처리) DB 접근
class CareTaskRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db

    # TODO: 조회/저장 쿼리 추가


def get_care_task_repository(db: AsyncSession = Depends(get_postgresql_db)) -> CareTaskRepository:
    return CareTaskRepository(db)
