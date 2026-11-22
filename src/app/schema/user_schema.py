from datetime import date, datetime
from pydantic import BaseModel
from app.enum.user_enum import UserRole, SocialProvider, Gender
from app.schema.common_schema import BaseDTO


# JWT payload에 담기는 사용자 정보 (내부용이라 snake_case 그대로 사용)
# 역할(role)을 담아두면 의사 전용 API 권한 체크를 DB 조회 없이 할 수 있다.
class UserClaimDTO(BaseModel):
    id: int
    email: str
    role: UserRole
    social_provider: SocialProvider


# 소셜 회원가입 (role은 기본값 PATIENT)
class UserCreateDTO(BaseModel):
    email: str
    social_provider: SocialProvider
    social_id: str


# 사용자 정보 응답 (social_id 등 민감 정보는 제외)
class UserResponseDTO(BaseDTO):
    id: int
    email: str
    nickname: str | None = None
    role: UserRole
    social_provider: SocialProvider
    name: str | None = None
    gender: Gender | None = None
    birth_date: date | None = None
    doctor_id: int | None = None
    point_balance: int
    created_at: datetime


# 내 정보 수정 요청 (보낸 값만 수정: model_dump(exclude_unset=True))
class UserUpdateDTO(BaseDTO):
    nickname: str | None = None
    name: str | None = None
    gender: Gender | None = None
    birth_date: date | None = None
