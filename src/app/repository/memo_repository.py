from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from app.infrastructure.postgresql import get_postgresql_db
from fastapi import Depends

# 모델, ORM
from app.model.user_model import User
from app.model.care_relation_model import CareRelation
from app.model.doctor_memo_model import DoctorMemo
from sqlalchemy import insert, select, update, func

KST = timezone(timedelta(hours=9)) # UTC+9


class MemoRepository:

    # 생성자 주입
    def __init__(self, db: AsyncSession):
        self.db = db


    # 1. 담당 관계 확인 (내가 담당 중인 환자인가? 담당이 끝난 관계는 제외)
    async def exists_care_relation(self, doctor_id: int, patient_id: int) -> bool:
        query = (
            select(CareRelation.relation_id)
            .where(
                CareRelation.doctor_id == doctor_id,
                CareRelation.patient_id == patient_id,
                CareRelation.ended_at.is_(None)
            )
            .limit(1)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none() is not None


    # 2. 환자 조회 (팝업 헤더의 환자 이름용) - 탈퇴한 회원 제외
    async def find_patient_by_id(self, patient_id: int) -> User | None:
        query = (
            select(User)
            .where(
                User.id == patient_id,
                User.deleted_at.is_(None)
            )
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 3. 메모 목록 (삭제 제외)
    # - 고정 메모가 항상 위, 그 다음 작성일 기준 정렬
    # - 작성자 이름이 필요하므로 doctor 관계를 selectinload로 미리 불러온다. (비동기에서 지연 로딩 불가)
    async def find_memos(self, patient_id: int, pinned: bool | None, newest_first: bool) -> list[DoctorMemo]:
        query = (
            select(DoctorMemo)
            .options(selectinload(DoctorMemo.doctor))
            .where(
                DoctorMemo.patient_id == patient_id,
                DoctorMemo.deleted_at.is_(None)
            )
        )

        if pinned is not None:
            query = query.where(DoctorMemo.is_pinned.is_(pinned))

        created_order = DoctorMemo.created_at.desc() if newest_first else DoctorMemo.created_at.asc()
        id_order = DoctorMemo.id.desc() if newest_first else DoctorMemo.id.asc()
        query = query.order_by(DoctorMemo.is_pinned.desc(), created_order, id_order)

        result = await self.db.execute(query)
        return list(result.scalars().all())


    # 4. 메모 개수 (전체, 고정) - 삭제 제외
    async def count_memos(self, patient_id: int) -> tuple[int, int]:
        query = (
            select(
                func.count(DoctorMemo.id),
                func.count(DoctorMemo.id).filter(DoctorMemo.is_pinned.is_(True))
            )
            .where(
                DoctorMemo.patient_id == patient_id,
                DoctorMemo.deleted_at.is_(None)
            )
        )

        result = await self.db.execute(query)
        total_count, pinned_count = result.one()
        return total_count, pinned_count


    # 5. 메모 1건 조회 (삭제 제외)
    # - populate_existing: 수정 직후 다시 조회할 때 세션에 남은 옛 값 대신 DB 값으로 덮어쓴다.
    async def find_memo_by_id(self, memo_id: int) -> DoctorMemo | None:
        query = (
            select(DoctorMemo)
            .options(selectinload(DoctorMemo.doctor))
            .where(
                DoctorMemo.id == memo_id,
                DoctorMemo.deleted_at.is_(None)
            )
            .execution_options(populate_existing=True)
        )

        result = await self.db.execute(query)
        return result.scalar_one_or_none()


    # 6. 메모 작성 -> 새 메모 id
    # - created_at과 updated_at을 같은 값으로 넣어야 "수정됨"이 처음부터 뜨지 않는다.
    #   (기본값 lambda가 컬럼마다 따로 호출되면 몇 마이크로초 차이가 난다)
    async def create_memo(self, doctor_id: int, patient_id: int, memo_data: dict) -> int:
        now = datetime.now(KST)
        query = (
            insert(DoctorMemo)
            .values(
                doctor_id=doctor_id,
                patient_id=patient_id,
                created_at=now,
                updated_at=now,
                **memo_data
            )
        ).returning(DoctorMemo.id)

        result = await self.db.execute(query)
        memo_id = result.scalar_one()
        await self.db.commit()
        return memo_id


    # 7. 메모 수정·고정
    # - touch_updated_at=False(고정만 바꿈): updated_at을 지금 값 그대로 다시 넣어서
    #   모델의 onupdate가 동작하지 않게 한다. -> "수정됨"이 뜨지 않는다.
    async def update_memo(self, memo_id: int, update_data: dict, touch_updated_at: bool) -> bool:
        values = dict(update_data)
        if not touch_updated_at:
            values["updated_at"] = DoctorMemo.updated_at

        query = (
            update(DoctorMemo)
            .where(
                DoctorMemo.id == memo_id,
                DoctorMemo.deleted_at.is_(None)
            )
            .values(**values)
        )

        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0


    # 8. 메모 삭제 (soft delete)
    # - updated_at은 그대로 둔다.
    async def delete_memo(self, memo_id: int) -> bool:
        query = (
            update(DoctorMemo)
            .where(
                DoctorMemo.id == memo_id,
                DoctorMemo.deleted_at.is_(None)
            )
            .values(
                deleted_at=datetime.now(KST),
                updated_at=DoctorMemo.updated_at
            )
        )

        result = await self.db.execute(query)
        await self.db.commit()
        return result.rowcount > 0



# 주입 팩토리 메서드
def get_memo_repository(db: AsyncSession = Depends(get_postgresql_db)):
    return MemoRepository(db)
