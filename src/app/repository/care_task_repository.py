from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db
from datetime import date
from sqlalchemy import select, func
# 모델, ORM
from app.models.user_model import User
from app.models.mission_model import Mission
from app.models.user_mission_log_model import UserMissionLog
from app.enums.mission_enum import MissionType


# 오늘의 작은 돌봄 / 나만의 돌봄 (미션과 같은 개념으로 묶어서 처리) DB 접근
class CareTaskRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db

    # TODO: 조회/저장 쿼리 추가
    # 함수 내에서 commit하지 않는다. flush까지만
    # 포인트 잔액 + 포인트 내역 + 완료 기록을 한 번에 저장해야 해서, commit 시점은 service가 정함
    async def commit(self) -> None:
        await self.db.commit()

    async def flush(self) -> None:
            await self.db.flush()

    #1.회원 잠금 - 같은 회원의 체크 요청이 동시에 와도 하나씩 처리한다. (두 번 눌러도 한 번만 지급)
    async def lock_user(self, user_id:int) -> User | None:
         query = (
              select(User)
              .where(User.id == user_id,User.deleted_at.is_(None))
              .with_for_update()
              )
         result = await self.db.execute(query)
         return result.scalar_one_or_none()

    #2. 사용 중인 목표 목록 (표시 순서대로) - 일일목표 또는 보너스
    async def find_active_mission(self, mission_type: MissionType) -> list[Mission]:
         query = (
              select(Mission)
              .where(Mission.mission_type == mission_type, Mission.is_active.is_(True))
              .order_by(Mission.sort_order, Mission.mission_id)
         )
         result = await self.db.execute(query)
         return list(result.scalar().all())

    #3. 목표 1개
    async def find_mission(self, mission_id: int) -> Mission | None:
         query = select(Mission).where(Mission.mission_id == mission_id)
         result = await self.db.execute(query)
         return list(result.scalar_one_or_none())
         
    #4. 이름으로 사용 중인 일일목표 1개 (자동 완료: 일기&감정 기록&상담에서 부를 떄)
    async def find_active_daily_goal_by_name(self, name:str) -> Mission|None:
         query = (
              select(Mission)
              .where(
                   Mission.name == name, 
                   Mission.mission_type==MissionType.DAILY_GOAL,
                   Mission.is_active.is_(True)
              )
              .limit(1)
         )
         result = await self.db.execute(query)
         return result.scalars().first()

    #5. 사용 중인 모두 완료 보너스 1개
    async  




def get_care_task_repository(db: AsyncSession = Depends(get_postgresql_db)) -> CareTaskRepository:
    return CareTaskRepository(db)
