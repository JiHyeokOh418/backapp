from typing import Literal
from fastapi import Depends, HTTPException, status
from app.repository.memo_repository import MemoRepository, get_memo_repository
from app.model.doctor_memo_model import DoctorMemo
from app.schema.memo_schema import (
    MemoCreateDTO,
    MemoUpdateDTO,
    MemoResponseDTO,
    MemoPatientResponseDTO,
    MemoListResponseDTO,
)

# 이 컬럼이 바뀌었을 때만 "수정됨"으로 본다. (고정/고정 해제는 수정이 아님)
EDIT_FIELDS = ("category", "content")


# 예외처리, 서비스가 드러나도록 이름을 선정해서 제작
# 트랜잭션 관리
class MemoService:

    def __init__(self, repo: MemoRepository):
        self.repo = repo


    # ORM -> 응답 DTO (작성자 이름, 수정 여부를 채운다)
    @staticmethod
    def _to_response(memo: DoctorMemo) -> MemoResponseDTO:
        return MemoResponseDTO(
            id=memo.id,
            patient_id=memo.patient_id,
            doctor_id=memo.doctor_id,
            doctor_name=memo.doctor.name if memo.doctor else None,
            category=memo.category,
            content=memo.content,
            is_pinned=memo.is_pinned,
            is_edited=memo.updated_at > memo.created_at,
            created_at=memo.created_at,
            updated_at=memo.updated_at
        )


    # 담당 환자인지 확인 (보안-02, 공통-04) - 아니면 403
    async def _ensure_in_charge(self, doctor_id: int, patient_id: int) -> None:
        if not await self.repo.exists_care_relation(doctor_id, patient_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="담당 환자가 아닙니다."
            )


    # 내가 쓴 메모인지 확인 - 없거나 삭제됐으면 404, 작성자가 아니면 403
    async def _get_my_memo(self, doctor_id: int, memo_id: int) -> DoctorMemo:
        memo = await self.repo.find_memo_by_id(memo_id)

        if not memo:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="메모가 존재하지 않습니다."
            )

        if memo.doctor_id != doctor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="작성자만 수정·삭제할 수 있습니다."
            )

        return memo


    # 1. 메모 목록 (담당 의사 누구나 볼 수 있음)
    async def get_memos(
        self, doctor_id: int, patient_id: int, pinned: bool | None, sort: Literal["latest", "oldest"]
    ) -> MemoListResponseDTO:
        await self._ensure_in_charge(doctor_id, patient_id)

        patient = await self.repo.find_patient_by_id(patient_id)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="환자가 존재하지 않습니다."
            )

        memos = await self.repo.find_memos(patient_id, pinned, newest_first=(sort == "latest"))
        total_count, pinned_count = await self.repo.count_memos(patient_id)

        return MemoListResponseDTO(
            patient=MemoPatientResponseDTO.model_validate(patient),
            total_count=total_count,
            pinned_count=pinned_count,
            items=[self._to_response(memo) for memo in memos]
        )


    # 2. 메모 작성 (담당 환자에게만)
    async def create_memo(self, doctor_id: int, patient_id: int, memo: MemoCreateDTO) -> MemoResponseDTO:
        await self._ensure_in_charge(doctor_id, patient_id)

        memo_id = await self.repo.create_memo(doctor_id, patient_id, memo.model_dump())
        created_memo = await self.repo.find_memo_by_id(memo_id)
        return self._to_response(created_memo)


    # 3. 메모 수정·고정 (작성자만, 보낸 값만 수정)
    async def update_memo(self, doctor_id: int, memo_id: int, memo: MemoUpdateDTO) -> MemoResponseDTO:
        found_memo = await self._get_my_memo(doctor_id, memo_id)

        # exclude_unset: 보내지 않은 값 제외 / None: null로 보낸 값도 무시 (모든 컬럼이 NOT NULL)
        update_data = {
            key: value
            for key, value in memo.model_dump(exclude_unset=True).items()
            if value is not None
        }

        # 실제로 값이 바뀐 컬럼만 남긴다.
        update_data = {
            key: value
            for key, value in update_data.items()
            if getattr(found_memo, key) != value
        }

        if not update_data:
            return self._to_response(found_memo)

        # 분류나 내용이 바뀌었을 때만 updated_at 갱신 -> "수정됨"
        touch_updated_at = any(key in EDIT_FIELDS for key in update_data)
        await self.repo.update_memo(memo_id, update_data, touch_updated_at)

        updated_memo = await self.repo.find_memo_by_id(memo_id)
        return self._to_response(updated_memo)


    # 4. 메모 삭제 (작성자만, soft delete)
    async def delete_memo(self, doctor_id: int, memo_id: int) -> None:
        await self._get_my_memo(doctor_id, memo_id)
        await self.repo.delete_memo(memo_id)



# 레포지토리 주입 팩토리 함수
def get_memo_service(repo: MemoRepository = Depends(get_memo_repository)):
    return MemoService(repo)
