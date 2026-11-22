from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.dialects.postgresql import insert as pg_insert
from app.infrastructure.postgresql import get_postgresql_db
from fastapi import Depends

# 모델, ORM
from app.model.user_model import User
from app.model.admin_model import Admin
from app.model.hospital_model import Hospital
from app.model.doctor_profile_model import DoctorProfile
from app.model.doctor_verification_model import DoctorVerification
from app.enum.user_enum import UserRole, VerificationStatus
from sqlalchemy import insert, select, update, exists

KST = timezone(timedelta(hours=9)) # UTC+9


class DoctorVerificationRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db


    # 1. 병원 검색 (이름 부분 일치)
    async def find_hospitals(self, keyword: str, limit: int) -> list[Hospital]:
        query = (
            select(Hospital)
            .where(Hospital.name.ilike(f"%{keyword}%"))
            .order_by(Hospital.name)
            .limit(limit)
        )

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 2. 병원 존재 확인
    async def exists_hospital(self, hospital_id: int) -> bool:
        query = select(exists().where(Hospital.hospital_id == hospital_id))
        result = await self.db.execute(query)
        return result.scalar()


    # 3. 대기 중인 신청이 있는지
    async def exists_pending(self, user_id: int) -> bool:
        query = select(exists().where(
            DoctorVerification.user_id == user_id,
            DoctorVerification.status == VerificationStatus.PENDING
        ))
        result = await self.db.execute(query)
        return result.scalar()


    # 4. 신청 저장 -> 새 신청 id
    async def create_verification(self, user_id: int, verification_data: dict) -> int:
        query = (
            insert(DoctorVerification)
            .values(user_id=user_id, **verification_data)
        ).returning(DoctorVerification.id)

        result = await self.db.execute(query)
        verification_id = result.scalar_one()
        await self.db.commit()
        return verification_id


    # 5. 신청 1건 조회 (신청자·병원 이름 포함)
    # - populate_existing: 승인·반려 직후 다시 조회할 때 세션에 남은 옛 값 대신 DB 값으로 덮어쓴다.
    async def find_verification_by_id(self, verification_id: int) -> DoctorVerification | None:
        query = (
            select(DoctorVerification)
            .options(selectinload(DoctorVerification.user), selectinload(DoctorVerification.hospital))
            .where(DoctorVerification.id == verification_id)
            .execution_options(populate_existing=True)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 6. 내 최근 신청 1건
    async def find_latest_verification(self, user_id: int) -> DoctorVerification | None:
        query = (
            select(DoctorVerification)
            .options(selectinload(DoctorVerification.user), selectinload(DoctorVerification.hospital))
            .where(DoctorVerification.user_id == user_id)
            .order_by(DoctorVerification.created_at.desc(), DoctorVerification.id.desc())
            .limit(1)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 7. 신청 목록 (관리자) - 상태 필터, 오래된 신청부터
    async def find_verifications(self, status: VerificationStatus | None) -> list[DoctorVerification]:
        query = (
            select(DoctorVerification)
            .options(selectinload(DoctorVerification.user), selectinload(DoctorVerification.hospital))
            .order_by(DoctorVerification.created_at.asc(), DoctorVerification.id.asc())
        )

        if status is not None:
            query = query.where(DoctorVerification.status == status)

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 8. 관리자 id 조회 (관리자가 아니면 None)
    async def find_admin_id(self, user_id: int) -> int | None:
        query = select(Admin.id).where(Admin.user_id == user_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 9. 승인 (한 트랜잭션)
    # - 대기 중인 신청만 승인 -> users.role=doctor -> doctor_profiles 생성(이미 있으면 병원·분야 갱신)
    # - 이미 처리된 신청이면 False (동시에 두 관리자가 눌러도 한 번만 처리된다)
    async def approve_verification(self, verification_id: int, admin_id: int) -> bool:
        now = datetime.now(KST)
        query = (
            update(DoctorVerification)
            .where(
                DoctorVerification.id == verification_id,
                DoctorVerification.status == VerificationStatus.PENDING
            )
            .values(status=VerificationStatus.APPROVED, reviewed_by=admin_id, reviewed_at=now)
            .returning(DoctorVerification.user_id, DoctorVerification.hospital_id, DoctorVerification.specialty)
        )

        row = (await self.db.execute(query)).first()
        if not row:
            await self.db.rollback()
            return False

        user_id, hospital_id, specialty = row

        await self.db.execute(
            update(User).where(User.id == user_id).values(role=UserRole.DOCTOR)
        )

        profile_query = pg_insert(DoctorProfile).values(
            user_id=user_id, hospital_id=hospital_id, specialty=specialty, created_at=now
        )
        await self.db.execute(
            profile_query.on_conflict_do_update(
                index_elements=[DoctorProfile.user_id],
                set_={"hospital_id": hospital_id, "specialty": specialty}
            )
        )

        await self.db.commit()
        return True


    # 10. 반려 (대기 중인 신청만)
    async def reject_verification(self, verification_id: int, admin_id: int, reject_reason: str) -> bool:
        query = (
            update(DoctorVerification)
            .where(
                DoctorVerification.id == verification_id,
                DoctorVerification.status == VerificationStatus.PENDING
            )
            .values(
                status=VerificationStatus.REJECTED,
                reject_reason=reject_reason,
                reviewed_by=admin_id,
                reviewed_at=datetime.now(KST)
            )
        )

        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0



# 주입 팩토리 메서드
def get_doctor_verification_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return DoctorVerificationRepository(db)
