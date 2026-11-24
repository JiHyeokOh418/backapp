from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db

# 모델, ORM
from app.models.user_model import User
from app.models.user_setting_model import UserSetting
from app.models.care_relation_model import CareRelation


# 마이페이지 DB 접근 (조회/저장만 담당, 비즈니스 규칙은 service에서 처리)
class MypageRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db


    # 1. 내 정보 조회 - 탈퇴한 회원 제외
    async def find_user(self, user_id: int) -> User | None:
        query = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 2. 내 정보 수정
    async def update_user(self, user_id: int, update_data: dict) -> User | None:
        if not update_data:
            return await self.find_user(user_id)

        query = (
            update(User)
            .where(User.id == user_id, User.deleted_at.is_(None))
            .values(**update_data)
            .returning(User)
        )
        result = await self.db.execute(query)
        updated_user = result.scalar_one_or_none()
        await self.db.commit()
        return updated_user


    # 3. 현재 담당 중인 의사 목록 (담당이 끝난 관계는 제외)
    async def find_linked_doctors(self, patient_id: int) -> list[tuple[CareRelation, User]]:
        query = (
            select(CareRelation, User)
            .join(User, User.id == CareRelation.doctor_id)
            .where(
                CareRelation.patient_id == patient_id,
                CareRelation.ended_at.is_(None)
            )
        )
        result = await self.db.execute(query)
        return list(result.all())


    # 4. 설정 조회 - 없으면 None (서비스에서 기본값 처리)
    async def find_setting(self, user_id: int) -> UserSetting | None:
        query = select(UserSetting).where(UserSetting.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 5. 설정 저장 (없으면 생성, 있으면 보낸 값만 수정)
    async def upsert_setting(self, user_id: int, setting_data: dict) -> UserSetting:
        query = (
            pg_insert(UserSetting)
            .values(user_id=user_id, **setting_data)
            .on_conflict_do_update(
                index_elements=[UserSetting.user_id],
                set_=setting_data
            )
            if setting_data
            else pg_insert(UserSetting).values(user_id=user_id).on_conflict_do_nothing()
        )
        await self.db.execute(query)
        await self.db.commit()
        return await self.find_setting(user_id)



def get_mypage_repository(db: AsyncSession = Depends(get_postgresql_db)) -> MypageRepository:
    return MypageRepository(db)
