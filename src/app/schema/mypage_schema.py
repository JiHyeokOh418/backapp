from datetime import date, datetime
from app.enums.user_enum import UserGender
from app.schema.common_schema import BaseDTO


# 마이페이지 요청/응답 DTO
# 규칙: BaseDTO 상속, XxxCreateDTO / XxxUpdateDTO / XxxResponseDTO 이름 사용

# 연결된 진료 (현재 담당 의사)
class LinkedDoctorResponseDTO(BaseDTO):
    doctor_id: int
    name: str | None = None
    nickname: str | None = None
    started_at: datetime | None = None


# 설정 응답
class UserSettingResponseDTO(BaseDTO):
    hide_stats: bool
    share_with_doctor: bool


# 설정 수정 요청 (보낸 값만 수정)
class UserSettingUpdateDTO(BaseDTO):
    hide_stats: bool | None = None
    share_with_doctor: bool | None = None


# 내 정보 페이지 응답 (기본 정보 + 연결된 진료 + 공유 설정)
class MyProfileResponseDTO(BaseDTO):
    id: int
    email: str
    nickname: str | None = None
    name: str | None = None
    gender: UserGender | None = None
    birth_date: date | None = None
    linked_doctors: list[LinkedDoctorResponseDTO] = []
    setting: UserSettingResponseDTO


# 프로필 카드 (마이페이지 메인 상단)
class MypageProfileCardDTO(BaseDTO):
    nickname: str | None = None
    today: date
    days_together: int


# 마이페이지 메인 요약
# - 오늘의 작은 돌봄, 이번 주 마음 흐름은 해당 기능 구현 후 채운다.
class MypageSummaryResponseDTO(BaseDTO):
    profile: MypageProfileCardDTO
    setting: UserSettingResponseDTO


# 내 정보 수정 요청 (닉네임, 이름, 생년월일, 성별) - 보낸 값만 수정
class MyProfileUpdateDTO(BaseDTO):
    nickname: str | None = None
    name: str | None = None
    gender: UserGender | None = None
    birth_date: date | None = None
