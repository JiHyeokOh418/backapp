from datetime import datetime
from pydantic import Field
from app.enum.user_enum import VerificationStatus
from app.schema.common_schema import BaseDTO


# 병원 검색 결과 (D-03 소속 병원 선택)
class HospitalResponseDTO(BaseDTO):
    hospital_id: int
    name: str
    address: str | None = None
    sido: str | None = None
    sigungu: str | None = None


# 의사 승인 신청 (D-03)
# - license_file_url: 면허 사본 저장 위치가 미정(ERD)이라 업로드된 경로를 문자열로만 받는다.
class DoctorVerificationCreateDTO(BaseDTO):
    hospital_id: int
    license_number: str = Field(min_length=1, max_length=50)
    specialty: str | None = Field(default=None, max_length=50)
    license_file_url: str | None = Field(default=None, max_length=500)


# 반려 요청 (관리자)
class DoctorVerificationRejectDTO(BaseDTO):
    reject_reason: str = Field(min_length=1)


# 신청 응답
class DoctorVerificationResponseDTO(BaseDTO):
    id: int
    user_id: int
    user_name: str | None = None
    user_email: str | None = None
    hospital_id: int
    hospital_name: str | None = None
    license_number: str
    specialty: str | None = None
    license_file_url: str | None = None
    status: VerificationStatus
    reject_reason: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime


# 내 신청 상태 (D-04)
# - verification: 신청한 적이 없으면 null -> 프론트는 D-03(신청 화면)으로
# - relogin_required: 승인됐지만 지금 토큰의 role이 아직 patient -> 다시 로그인해야 의사 기능 사용 가능
class MyVerificationResponseDTO(BaseDTO):
    verification: DoctorVerificationResponseDTO | None = None
    relogin_required: bool = False
