from datetime import datetime
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from app.infrastructure.postgresql import get_postgresql_db

# 모델, ORM
from app.models.user_model import User
from app.models.user_setting_model import UserSetting
from app.models.care_relation_model import CareRelation
from app.models.doctor_profile_model import DoctorProfile
from app.models.hospital_model import Hospital
from app.models.appointment_model import Appointment
from app.enums.appointment_enum import AppointmentStatus


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


    # 3-1. 현재 담당 의사 + 소속 병원 (내 정보 > 연결된 진료 카드)
    # - 의사 정보(doctor_profiles)가 아직 없는 의사도 목록에서 빠지지 않게 outerjoin
    async def find_linked_doctors_with_hospital(self, patient_id: int) -> list[tuple[CareRelation, User, Hospital | None]]:
        query = (
            select(CareRelation, User, Hospital)
            .join(User, User.id == CareRelation.doctor_id)
            .outerjoin(DoctorProfile, DoctorProfile.user_id == CareRelation.doctor_id)
            .outerjoin(Hospital, Hospital.hospital_id == DoctorProfile.hospital_id)
            .where(
                CareRelation.patient_id == patient_id,
                CareRelation.ended_at.is_(None)
            )
            .order_by(CareRelation.started_at.desc())
        )
        result = await self.db.execute(query)
        return list(result.all())


    # 3-2. 그 의사와의 다음 진료 시각 (지금 이후, 가장 가까운 1건)
    # - 취소·노쇼·완료된 예약은 빼고, 예약됨(booked)·대기(waiting)만 본다
    async def find_next_appointment_at(
        self, patient_id: int, doctor_id: int, now: datetime
    ) -> datetime | None:
        query = (
            select(Appointment.scheduled_at)
            .where(
                Appointment.patient_id == patient_id,
                Appointment.doctor_id == doctor_id,
                Appointment.status.in_([AppointmentStatus.BOOKED, AppointmentStatus.WAITING]),
                Appointment.scheduled_at >= now
            )
            .order_by(Appointment.scheduled_at.asc())
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()


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

    
    # 5-1. 설정 수정 시각·동의 변경 시각 기록
    # - upsert(INSERT ... ON CONFLICT)에서는 모델의 onupdate가 동작하지 않아 따로 기록한다
    async def update_setting_times(self, user_id: int, consent_changed: bool, now: datetime) -> None:
        values = {"updated_at": now}
        if consent_changed:
            values["consent_updated_at"] = now

        query = (
            update(UserSetting)
            .where(UserSetting.user_id == user_id)
            .values(**values)
        )
        await self.db.execute(query)
        await self.db.commit()

def get_mypage_repository(db: AsyncSession = Depends(get_postgresql_db)) -> MypageRepository:
    return MypageRepository(db)
