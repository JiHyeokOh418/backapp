from datetime import date, datetime
from datetime import timedelta, timezone
from pydantic import field_validator
from pydantic import model_validator
from app.enums.user_enum import UserGender
from app.schema.common_schema import BaseDTO

KST = timezone(timedelta(hours=9)) # UTC+9

# 마이페이지 요청/응답 DTO
# 규칙: BaseDTO 상속, XxxCreateDTO / XxxUpdateDTO / XxxResponseDTO 이름 사용

# 연결된 진료 (현재 담당 의사)
class LinkedDoctorResponseDTO(BaseDTO):
    doctor_id: int
    name: str | None = None
    nickname: str | None = None
    started_at: datetime | None = None
    hospital_id: int | None = None 
    hospital_name: str | None = None 
    next_appointment_at: datetime | None = None


# 설정 응답
class UserSettingResponseDTO(BaseDTO):
    hide_stats: bool
    share_with_doctor: bool | None = None
    share_report: bool = True   #마음 리포트 선생님께 공유
    share_diary: bool = False   #일기 내용 공유하기
    diary_ai_consent: bool = False  #일기 AI 분석 동의


# 설정 수정 요청 (보낸 값만 수정)
class UserSettingUpdateDTO(BaseDTO):
    hide_stats: bool | None = None
    share_with_doctor: bool | None = None
    share_report: bool | None = None
    share_diary: bool | None = None
    diary_ai_consent: bool | None = None

    # 예전 이름(share_with_doctor)이 비어 있으면 같은 뜻인 share_report 값을 채운다
    @model_validator(mode="after")
    def fill_share_with_doctor(self):
        if self.share_with_doctor is None:
            self.share_with_doctor = self.share_report
        return self


# 내 정보 페이지 응답 (기본 정보 + 연결된 진료 + 공유 설정)
class MyProfileResponseDTO(BaseDTO):
    id: int
    email: str | None = None
    nickname: str | None = None
    name: str | None = None
    gender: UserGender | None = None
    birth_date: date | None = None
    linked_doctors: list[LinkedDoctorResponseDTO] = []
    setting: UserSettingResponseDTO
    age: int | None = None 
    joined_at: date | None = None   #가입일
    days_since_join: int | None = None  #가입한 지 N일째


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

# 닉네임: 앞뒤 공백을 지우고 2~10자인지 확인 (결정-07)
    @field_validator("nickname", mode="before")
    @classmethod
    def check_nickname(cls,value):
        if isinstance(value,str):
            value = value.strip()
            if not 2 <= len(value) <= 10:
                raise ValueError("닉네임은 2~10자로 입력해 주세요.")
        return value

# 이름: 앞뒤 공백을 지우고 1~50자인지 확인 (users.name VARCHAR(50))
    @field_validator("name", mode="before")
    @classmethod
    def check_name(cls, value):
        if isinstance(value, str):
            value = value.strip()
            if not 1 <= len(value) <= 50:
                raise ValueError("이름은 1~50자로 입력해 주세요.")
        return value

# 생년월일: 오늘(KST)보다 뒤일 수 없음
    @field_validator("birth_date")
    @classmethod
    def check_birth_date(cls,value):
        if value is not None and value > datetime.now(KST).date():
            raise ValueError("잘못된 생년월일이에요.")
        return value


    
