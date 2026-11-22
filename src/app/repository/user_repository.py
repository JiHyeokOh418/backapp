from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.postgresql import get_postgresql_db
from fastapi import Depends

# 모델, ORM
from app.model.user_model import User
from app.enum.user_enum import SocialProvider
from app.schema.user_schema import UserCreateDTO, UserClaimDTO
from sqlalchemy import insert, select, update

KST = timezone(timedelta(hours=9)) # UTC+9


class UserRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db


    # 순수 함수
    # 1. 회원 정보 조회(id) - 탈퇴한 회원 제외
    async def find_user_by_id(self, id: int) -> User | None:
        query = (
            select(User)
            .where(
                User.id == id,
                User.deleted_at.is_(None)
            )
        )

        result = await self.db.execute(query)
        found_user = result.scalar_one_or_none()
        return found_user


    # 2. 회원 정보 조회(social_provider, social_id) - 소셜 로그인용
    async def find_user_by_social(self, social_provider: SocialProvider, social_id: str) -> User | None:
        query = (
            select(User)
            .where(
                User.social_provider == social_provider,
                User.social_id == social_id,
                User.deleted_at.is_(None)
            )
        )

        result = await self.db.execute(query)
        found_user = result.scalar_one_or_none()
        return found_user


    # 3. 소셜 회원가입
    async def create_user(self, user: UserCreateDTO) -> UserClaimDTO:
        # pydantic -> dict
        new_user = user.model_dump()
        query = (
            insert(User)
            .values(**new_user)
        ).returning(
            User.id,
            User.email,
            User.role,
            User.social_provider
        )

        result = await self.db.execute(query)
        # 필요한 값을 리턴(id, email, role, social_provider)
        id, email, role, social_provider = result.first()

        payload = {
            "id": id,
            "email": email,
            "role": role,
            "social_provider": social_provider
        }

        # dict -> pydantic
        claim_dto = UserClaimDTO.model_validate(payload)

        await self.db.commit()
        return claim_dto


    # 4. 회원 정보 수정
    async def update_user(self, id: int, update_data: dict) -> User | None:
        if not update_data:
            return await self.find_user_by_id(id)

        query = (
            update(User)
            .where(
                User.id == id,
                User.deleted_at.is_(None)
            )
            .values(**update_data)
            .returning(User)
        )

        result = await self.db.execute(query)
        updated_user = result.scalar_one_or_none()
        await self.db.commit()
        return updated_user


    # 5. 회원 탈퇴 (soft delete)
    # - 연관 데이터(일기, 상담 기록 등)를 보존하기 위해 행은 남기고 deleted_at만 기록한다.
    # - social_id를 비워서 같은 소셜 계정으로 재가입할 수 있게 한다. (unique 제약 회피)
    async def withdraw_user(self, id: int) -> bool:
        query = (
            update(User)
            .where(
                User.id == id,
                User.deleted_at.is_(None)
            )
            .values(
                deleted_at=datetime.now(KST),
                social_id=None
            )
        )

        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0



# 주입 팩토리 메서드
def get_user_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return UserRepository(db)
