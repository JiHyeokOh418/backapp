from fastapi import Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from app.repository.doctor_verification_repository import (
    DoctorVerificationRepository, get_doctor_verification_repository
)
from app.model.doctor_verification_model import DoctorVerification
from app.enum.user_enum import UserRole, VerificationStatus
from app.schema.user_schema import UserClaimDTO
from app.schema.doctor_verification_schema import (
    HospitalResponseDTO,
    DoctorVerificationCreateDTO,
    DoctorVerificationResponseDTO,
    MyVerificationResponseDTO,
)


# 의사 승인 흐름 (결정: 관리자가 면허 확인 후 승인 -> role=doctor, 승인 후 재로그인)
# 예외처리, 트랜잭션 관리
class DoctorVerificationService:

    def __init__(self, repo: DoctorVerificationRepository):
        self.repo = repo


    # ORM -> 응답 DTO (신청자·병원 이름을 채운다)
    @staticmethod
    def _to_response(verification: DoctorVerification) -> DoctorVerificationResponseDTO:
        return DoctorVerificationResponseDTO(
            id=verification.id,
            user_id=verification.user_id,
            user_name=verification.user.name if verification.user else None,
            user_email=verification.user.email if verification.user else None,
            hospital_id=verification.hospital_id,
            hospital_name=verification.hospital.name if verification.hospital else None,
            license_number=verification.license_number,
            specialty=verification.specialty,
            license_file_url=verification.license_file_url,
            status=verification.status,
            reject_reason=verification.reject_reason,
            reviewed_at=verification.reviewed_at,
            created_at=verification.created_at
        )


    # 관리자인지 확인 -> 관리자 id (아니면 403)
    async def _get_admin_id(self, user_id: int) -> int:
        admin_id = await self.repo.find_admin_id(user_id)

        if admin_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="관리자만 사용할 수 있습니다."
            )

        return admin_id


    # 1. 병원 검색
    async def search_hospitals(self, keyword: str, limit: int) -> list[HospitalResponseDTO]:
        hospitals = await self.repo.find_hospitals(keyword, limit)
        return [HospitalResponseDTO.model_validate(hospital) for hospital in hospitals]


    # 2. 의사 승인 신청
    # - 이미 의사이거나 대기 중인 신청이 있으면 409
    async def apply(self, current_user: UserClaimDTO, verification: DoctorVerificationCreateDTO) -> DoctorVerificationResponseDTO:
        if current_user.role == UserRole.DOCTOR:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="이미 의사로 승인된 계정입니다."
            )

        if not await self.repo.exists_hospital(verification.hospital_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="병원이 존재하지 않습니다."
            )

        pending_conflict = HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="승인 대기 중인 신청이 이미 있습니다."
        )
        if await self.repo.exists_pending(current_user.id):
            raise pending_conflict

        try:
            verification_id = await self.repo.create_verification(current_user.id, verification.model_dump())
        except IntegrityError:
            # 동시에 두 번 신청한 경우 (pending 부분 유니크 인덱스)
            raise pending_conflict

        created = await self.repo.find_verification_by_id(verification_id)
        return self._to_response(created)


    # 3. 내 신청 상태 (D-04)
    async def get_my_verification(self, current_user: UserClaimDTO) -> MyVerificationResponseDTO:
        latest = await self.repo.find_latest_verification(current_user.id)

        if not latest:
            return MyVerificationResponseDTO()

        return MyVerificationResponseDTO(
            verification=self._to_response(latest),
            relogin_required=(
                latest.status == VerificationStatus.APPROVED and current_user.role != UserRole.DOCTOR
            )
        )


    # 4. 신청 목록 (관리자)
    async def get_verifications(self, user_id: int, verification_status: VerificationStatus | None) -> list[DoctorVerificationResponseDTO]:
        await self._get_admin_id(user_id)
        verifications = await self.repo.find_verifications(verification_status)
        return [self._to_response(verification) for verification in verifications]


    # 대기 중인 신청인지 확인 (승인·반려 실패 시 404/409 구분)
    async def _raise_not_pending(self, verification_id: int) -> None:
        if not await self.repo.find_verification_by_id(verification_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="신청이 존재하지 않습니다."
            )

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 처리된 신청입니다."
        )


    # 5. 승인 (관리자) -> role=doctor, doctor_profiles 생성
    # - 신청자의 토큰은 아직 patient다. 다시 로그인해야 의사 기능을 쓸 수 있다.
    async def approve(self, user_id: int, verification_id: int) -> DoctorVerificationResponseDTO:
        admin_id = await self._get_admin_id(user_id)

        if not await self.repo.approve_verification(verification_id, admin_id):
            await self._raise_not_pending(verification_id)

        approved = await self.repo.find_verification_by_id(verification_id)
        return self._to_response(approved)


    # 6. 반려 (관리자)
    async def reject(self, user_id: int, verification_id: int, reject_reason: str) -> DoctorVerificationResponseDTO:
        admin_id = await self._get_admin_id(user_id)

        if not await self.repo.reject_verification(verification_id, admin_id, reject_reason):
            await self._raise_not_pending(verification_id)

        rejected = await self.repo.find_verification_by_id(verification_id)
        return self._to_response(rejected)



# 레포지토리 주입 팩토리 함수
def get_doctor_verification_service(
    repo: DoctorVerificationRepository = Depends(get_doctor_verification_repository)
):
    return DoctorVerificationService(repo)
